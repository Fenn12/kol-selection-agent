#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Web 工作台（零依赖，标准库 http.server）。

启动：
    python web/server.py
    然后浏览器打开 http://127.0.0.1:8765

接口：
    GET  /api/overview?budget=8000   驾驶舱数据（销售结构 / 监测告警 / 复盘）
    POST /api/run                    跑一次 agent，返回 trace 与结论
    GET  /api/brief?ids=K001,K002    生成合作 brief（Markdown）
    GET  /api/outreach?ids=K001      生成邀约话术（JSON，可直接复制）
    GET  /api/report                 生成日报（Markdown）
    POST /api/notify                 推送日报（默认 dry-run，落盘到 outbox/）
    GET  /api/datasource             当前数据源
"""

import json
import os
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agent import datasource, llm, notify, planner, runner, tools_extra  # noqa: E402
from agent.core import parse_product_sales  # noqa: E402

STATIC = os.path.join(HERE, "static")
PORT = int(os.environ.get("PORT", "8765"))

# 最近一次运行结果，供前端刷新后恢复
LAST = {"rec": None, "lock": threading.Lock()}


def overview(budget=8000.0):
    """驾驶舱：不跑 agent，直接取各工具的聚合结果，保证秒开。"""
    stats = parse_product_sales()
    mon = tools_extra.monitor_scan()
    rev = tools_extra.review_campaign("content_type")

    p0 = [a for a in mon.get("alerts", []) if a["severity"] == "P0"]
    p1 = [a for a in mon.get("alerts", []) if a["severity"] == "P1"]

    # 待办：P0 优先，每条给出「查什么」
    todos = []
    for a in p0 + p1:
        todos.append({
            "level": a["severity"], "kol_id": a["kol_id"], "rule": a["rule"],
            "delta": a["delta_pct"], "hint": a["hint"],
        })

    return {
        "product": {
            "channel": stats.get("渠道销量结构", {}),
            "aov": stats.get("估算客单价"),
            "aov_conf": stats.get("客单价_置信度"),
            "sales_mid": stats.get("销售额_中值"),
            "creators": stats.get("达人效率", {}),
        },
        "monitor": {
            "alert_count": mon.get("alert_count"),
            "p0": len(p0), "p1": len(p1),
            "scanned": mon.get("scanned_kols"),
            "window": mon.get("window"),
        },
        "review": {
            "overall": rev.get("overall"),
            "rows": rev.get("rows", []),
            "best": rev.get("best"), "worst": rev.get("worst"),
        },
        "todos": todos[:8],
        "budget": budget,
        "llm": llm.available(),
        "datasource": datasource.describe(),
    }


def run_agent(goal, budget, planner_name):
    use_llm = planner_name == "llm" and llm.available()
    p = (planner.LLMPlanner() if use_llm
         else planner.RulePlanner(budget=budget))
    agent = runner.Agent(p, trace_dir=os.path.join(ROOT, "traces"))
    rec = agent.run(goal)

    # 补上前端要用的结构化视图
    ctx = agent.ctx
    view = {
        "plan": (ctx.allocation or {}).get("plan", []),
        "allocation": ctx.allocation or {},
        "scored_tiers": (ctx.scored or {}).get("tier_count", {}),
        "alerts": (ctx.monitor or {}).get("alerts", []),
        "review": (ctx.review or {}).get("rows", []),
        "funnels": ctx.funnels,
        "rewrites": [{k: w.get(k) for k in ("source_id", "title", "body", "mode",
                                            "changes", "before_compliance", "after_compliance",
                                            "length", "target_length")}
                     for w in ctx.rewrites],
        "briefs": (ctx.brief or {}),
    }
    rec["view"] = view
    with LAST["lock"]:
        LAST["rec"] = rec
    return rec


class Handler(BaseHTTPRequestHandler):
    server_version = "KOLWorkbench/1.0"

    def log_message(self, fmt, *args):  # 静默掉默认日志，避免刷屏
        pass

    # ---------- 响应工具 ----------

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    # ---------- 路由 ----------

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path, qs = parsed.path, urllib.parse.parse_qs(parsed.query)

        if path in ("/", "/index.html"):
            return self._file("index.html", "text/html; charset=utf-8", subdir="static")
        if path.startswith("/static/"):
            name = path[len("/static/"):]
            ctype = {".css": "text/css; charset=utf-8",
                     ".js": "application/javascript; charset=utf-8",
                     ".svg": "image/svg+xml"}.get(os.path.splitext(name)[1], "application/octet-stream")
            return self._file(name, ctype, subdir="static")

        if path == "/api/overview":
            try:
                b = float(qs.get("budget", ["8000"])[0])
            except ValueError:
                b = 8000.0
            try:
                return self._json(overview(b))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        if path == "/api/last":
            with LAST["lock"]:
                return self._json(LAST["rec"] or {})

        if path == "/api/brief":
            ids = [x for x in qs.get("ids", [""])[0].split(",") if x]
            if not ids:
                return self._json({"error": "缺少 ids"}, 400)
            out = tools_extra.draft_collab_brief(ids)
            md = "\n\n---\n\n".join(b.get("content", "") for b in out.get("briefs", [])
                                    if b.get("content"))
            return self._send(200, md, "text/markdown; charset=utf-8")

        if path == "/api/outreach":
            ids = [x for x in qs.get("ids", [""])[0].split(",") if x]
            if not ids:
                return self._json({"error": "缺少 ids"}, 400)
            return self._json(tools_extra.draft_outreach_message(
                ids, channel=qs.get("channel", ["私信"])[0]))

        if path == "/api/report":
            try:
                b = float(qs.get("budget", ["8000"])[0])
            except ValueError:
                b = 8000.0
            rep = tools_extra.compose_daily_report(budget=b)
            return self._send(200, rep["markdown"], "text/markdown; charset=utf-8")

        if path == "/api/datasource":
            return self._json(datasource.describe())

        if path == "/api/export":
            with LAST["lock"]:
                rec = LAST["rec"]
            if not rec:
                return self._json({"error": "还没有运行结果"}, 400)
            plan = rec.get("view", {}).get("plan", [])
            lines = ["kol_id,handle,platform,tier,score,quote"]
            lines += [f"{p['kol_id']},{p['handle']},{p['platform']},{p['tier']},{p['score']},{p['quote']}"
                      for p in plan]
            return self._send(200, "\ufeff" + "\n".join(lines), "text/csv; charset=utf-8")

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/api/run", "/api/notify"):
            return self._json({"error": "not found"}, 404)

        length = int(self.headers.get("Content-Length") or 0)
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return self._json({"error": "请求体不是合法 JSON"}, 400)

        goal = (payload.get("goal") or "").strip() or "指压板新品起量"
        try:
            budget = float(payload.get("budget") or 8000)
        except (TypeError, ValueError):
            budget = 8000.0
        planner_name = payload.get("planner") or ("llm" if llm.available() else "rule")

        if parsed.path == "/api/run":
            try:
                rec = run_agent(goal, budget, planner_name)
                return self._json(rec)
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        if parsed.path == "/api/notify":
            rep = tools_extra.compose_daily_report(budget=budget)
            res = notify.send(f"[投放监测] P0 {rep['p0']} / P1 {rep['p1']}",
                              rep["markdown"],
                              dry_run=True if payload.get("dry_run", True) else None)
            return self._json(res)

    # ---------- 静态文件 ----------

    def _file(self, name, ctype, subdir=""):
        base = os.path.join(HERE, subdir) if subdir else HERE
        p = os.path.join(base, name)
        if not os.path.exists(p):
            return self._send(404, "not found", "text/plain; charset=utf-8")
        with open(p, "rb") as f:
            return self._send(200, f.read(), ctype)


def main():
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"KOL 运营工作台已启动：http://127.0.0.1:{PORT}")
    print(f"模型：{'已配置，可用 LLM 规划器' if llm.available() else '未配置 key，使用离线规则规划器'}")
    print("Ctrl+C 停止")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
