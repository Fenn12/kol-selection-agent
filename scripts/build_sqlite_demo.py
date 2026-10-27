#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 data/*.csv 灌进 SQLite，用来演示「SQL 数据源」这条路真的能走通。

    python scripts/build_sqlite_demo.py
    KOL_DATASOURCE=sql KOL_DB_URL=sqlite:///data/demo.db python run_agent.py --goal "起量"
"""

import csv
import json
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
SQL = os.path.join(ROOT, "sql")
DB = os.path.join(DATA, "demo.db")


def rows(name):
    with open(os.path.join(DATA, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def insert(conn, table, data, ints=(), floats=()):
    if not data:
        return 0
    cols = list(data[0].keys())
    ph = ",".join("?" * len(cols))
    sql = f'INSERT OR REPLACE INTO {table} ({",".join(chr(34)+c+chr(34) for c in cols)}) VALUES ({ph})'
    vals = []
    for r in data:
        v = []
        for c in cols:
            x = r.get(c)
            if c in ints and x not in (None, ""):
                x = int(float(x))
            elif c in floats and x not in (None, ""):
                x = float(x)
            v.append(x)
        vals.append(v)
    conn.executemany(sql, vals)
    return len(vals)


def main():
    if os.path.exists(DB):
        os.remove(DB)
    conn = sqlite3.connect(DB)
    conn.executescript(open(os.path.join(SQL, "schema_enterprise.sql"), encoding="utf-8").read())

    n1 = insert(conn, "product_sales_daily", rows("product_sales.sample.csv"),
                ints=("浏览量", "带货视频", "带货直播", "带货达人", "视频带货达人", "直播带货达人"))
    n2 = insert(conn, "dim_kol", rows("candidates.csv"),
                ints=("followers", "exposure_30d", "store_uv_30d", "orders_30d"),
                floats=("engagement_rate", "viral_rate", "comment_intent", "post_stability",
                        "aov", "quote", "fulfill_rate", "repurchase_rate"))
    n3 = insert(conn, "fact_kol_daily", rows("campaign_performance.csv"),
                ints=("impressions", "clicks", "store_uv", "orders"),
                floats=("gmv", "spend", "aov"))
    samples = json.load(open(os.path.join(DATA, "content_samples.json"), encoding="utf-8"))
    n4 = insert(conn, "dim_content_sample", samples)
    conn.commit()
    conn.close()

    print(f"已生成 {DB}")
    print(f"  product_sales_daily {n1} 行 ｜ dim_kol {n2} 行 ｜ fact_kol_daily {n3} 行 ｜ content_sample {n4} 行")
    print("验证：")
    print("  KOL_DATASOURCE=sql KOL_DB_URL=sqlite:///data/demo.db python -c "
          "\"from agent import datasource;print(datasource.describe())\"")


if __name__ == "__main__":
    main()
