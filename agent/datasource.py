#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据源抽象层。

三种实现，同一套接口，靠环境变量切换：

    KOL_DATASOURCE=csv   （默认）读 data/*.csv
    KOL_DATASOURCE=sql   读数据库，用 sql/mapping.json 里的 SQL
    KOL_DATASOURCE=http  调内网 API

接入企业库的两种方式（都不需要改业务代码）：

    A. 只改 SQL：把 sql/mapping.json 里的表名/字段名换成你自己的，
       设置 KOL_DATASOURCE=sql 与 KOL_DB_URL。
    B. 自己实现连接：设置 KOL_DB_MODULE=my_pkg.mydb，该模块暴露 connect()
       返回任意 DB-API 连接对象（pymysql / psycopg2 / oracledb 都行）。

设计约束：
    所有 source 返回的都是 list[dict]，字段名用本仓库内部标准名。
    字段映射在 mapping.json 的 "columns" 段完成，业务层不感知差异。
"""

import csv
import json
import os
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
SQL_DIR = os.path.join(ROOT, "sql")

DATASETS = ("product_sales", "candidates", "campaign", "content_samples")


class DataSourceError(RuntimeError):
    pass


# ------------------------------------------------------------
# 基类
# ------------------------------------------------------------

class DataSource:
    name = "base"

    def load(self, dataset):
        """返回 list[dict]；content_samples 也统一成 rows。"""
        raise NotImplementedError

    def describe(self):
        return {"source": self.name}


# ------------------------------------------------------------
# CSV（默认）
# ------------------------------------------------------------

CSV_FILES = {
    "product_sales": "product_sales.sample.csv",
    "candidates": "candidates.csv",
    "campaign": "campaign_performance.csv",
}


class CsvSource(DataSource):
    name = "csv"

    def load(self, dataset):
        if dataset == "content_samples":
            p = os.path.join(DATA, "content_samples.json")
            if not os.path.exists(p):
                raise DataSourceError(f"缺少 {p}")
            return json.load(open(p, encoding="utf-8"))
        fname = CSV_FILES.get(dataset)
        if not fname:
            raise DataSourceError(f"未知数据集 {dataset}")
        p = os.path.join(DATA, fname)
        if not os.path.exists(p):
            raise DataSourceError(f"缺少数据文件 {p}")
        with open(p, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def describe(self):
        return {"source": "csv", "path": DATA}


# ------------------------------------------------------------
# SQL
# ------------------------------------------------------------

def _load_mapping():
    p = os.path.join(SQL_DIR, "mapping.json")
    if not os.path.exists(p):
        raise DataSourceError(f"缺少 sql/mapping.json（SQL 数据源的字段映射）")
    return json.load(open(p, encoding="utf-8"))


def _connect(url=None, module=None):
    """建立数据库连接。

    优先用 KOL_DB_MODULE（企业自定义），否则按 URL scheme 选内置驱动。
    """
    module = module or os.getenv("KOL_DB_MODULE")
    if module:
        import importlib
        mod = importlib.import_module(module)
        if not hasattr(mod, "connect"):
            raise DataSourceError(f"{module} 没有暴露 connect()")
        return mod.connect()

    url = url or os.getenv("KOL_DB_URL")
    if not url:
        raise DataSourceError("SQL 数据源需要 KOL_DB_URL 或 KOL_DB_MODULE")

    parsed = urllib.parse.urlparse(url)
    scheme = parsed.scheme.lower()

    if scheme == "sqlite":
        import sqlite3
        path = url.split("sqlite:///", 1)[-1]
        return sqlite3.connect(path)

    if scheme in ("mysql", "mysql+pymysql"):
        try:
            import pymysql  # noqa
        except ImportError:
            raise DataSourceError("MySQL 需要 pip install pymysql")
        return pymysql.connect(host=parsed.hostname, port=parsed.port or 3306,
                               user=urllib.parse.unquote(parsed.username or ""),
                               password=urllib.parse.unquote(parsed.password or ""),
                               database=parsed.path.lstrip("/"), charset="utf8mb4")

    if scheme in ("postgres", "postgresql", "postgres+psycopg2"):
        try:
            import psycopg2  # noqa
        except ImportError:
            raise DataSourceError("PostgreSQL 需要 pip install psycopg2-binary")
        return psycopg2.connect(url)

    raise DataSourceError(f"未支持的数据库类型：{scheme}（可用 KOL_DB_MODULE 自定义）")


class SqlSource(DataSource):
    name = "sql"

    def __init__(self):
        self.mapping = _load_mapping()
        self._conn = None

    def _cursor(self):
        if self._conn is None:
            self._conn = _connect()
        return self._conn.cursor()

    def load(self, dataset):
        q = (self.mapping.get("queries") or {}).get(dataset)
        if not q:
            raise DataSourceError(f"mapping.json 缺少 {dataset} 的查询")
        cur = self._cursor()
        try:
            cur.execute(q)
            cols = [d[0] for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        except Exception as e:
            raise DataSourceError(f"查询 {dataset} 失败：{e}") from e

        aliases = (self.mapping.get("columns") or {}).get(dataset) or {}
        return [_apply_alias(r, aliases) for r in rows]

    def describe(self):
        return {"source": "sql",
                "url_scheme": urllib.parse.urlparse(os.getenv("KOL_DB_URL", "custom://")).scheme,
                "custom_module": os.getenv("KOL_DB_MODULE")}


def _apply_alias(row, aliases):
    """把企业字段名映射成内部标准名；未映射的字段原样保留。"""
    if not aliases:
        return row
    return {aliases.get(k, k): v for k, v in row.items()}


# ------------------------------------------------------------
# HTTP（内网 API）
# ------------------------------------------------------------

class HttpSource(DataSource):
    name = "http"

    def __init__(self):
        self.base = (os.getenv("KOL_API_BASE") or "").rstrip("/")
        self.token = os.getenv("KOL_API_TOKEN")
        if not self.base:
            raise DataSourceError("HTTP 数据源需要 KOL_API_BASE")

    def load(self, dataset):
        url = f"{self.base}/{dataset}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        if self.token:
            req.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            raise DataSourceError(f"请求 {url} 失败：{e}") from e

        if isinstance(data, dict) and "data" in data:
            data = data["data"]
        if not isinstance(data, list):
            raise DataSourceError(f"{dataset} 返回的不是数组")
        return data

    def describe(self):
        return {"source": "http", "base": self.base}


# ------------------------------------------------------------
# 单例
# ------------------------------------------------------------

_SOURCE = None


def get():
    global _SOURCE
    if _SOURCE is not None:
        return _SOURCE

    kind = (os.getenv("KOL_DATASOURCE") or "csv").lower()
    if kind == "csv":
        _SOURCE = CsvSource()
    elif kind == "sql":
        _SOURCE = SqlSource()
    elif kind == "http":
        _SOURCE = HttpSource()
    else:
        raise DataSourceError(f"KOL_DATASOURCE 只能是 csv / sql / http，收到 {kind}")
    return _SOURCE


def reset():
    """切换数据源后调用，清掉缓存。"""
    global _SOURCE
    _SOURCE = None


def load(dataset):
    return get().load(dataset)


def describe():
    try:
        return get().describe()
    except DataSourceError as e:
        return {"source": "error", "error": str(e)}
