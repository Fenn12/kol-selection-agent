#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Web 工作台（零依赖，标准库 http.server）。

启动：
    python web/server.py
    然后浏览器打开 http://127.0.0.1:8765

接口：
    GET  /api/overview?budget=8000   驾驶舱数据（销售结构 / 监测告警 / 复盘）
    GET  /api/candidates?budget=     候选池四维评分 + 分层 + 预算分配
    GET  /api/trend?days=30          按日投放趋势
    GET  /api/tasks?limit=12         最近运行记录（traces）
    POST /api/run                    跑一次 agent，返回 trace 与结论
    GET  /api/content/samples        内容样本 + 逐条合规预检
    POST /api/content/rewrite        多平台改写 + 改写前后合规对比
    GET  /api/brief?ids=K001,K002    生成合作 brief（Markdown）
    GET  /api/outreach?ids=K001      生成邀约话术（JSON，可直接复制）
    GET  /api/funnel?kol_id=K040     单达人漏斗诊断
    GET  /api/report                 生成日报（Markdown）
    GET  /api/reports                历史日报列表（outbox）
    GET  /api/reports/<file>         读取一份历史日报
    POST /api/notify                 推送日报（默认 dry-run，落盘到 outbox/）
    GET  /api/export?ids=            名单 CSV 导出（带 BOM）
    GET  /api/datasource             当前数据源
    GET  /api/llm/status             模型可用性与累计用量
    POST /api/llm/test               连通性自检
    POST /api/pipeline               企微消息 → 线索 → 评分 → 飞书 → 待发队列
"""

import json
import os
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from agent import core, datasource, env, llm, notify, pipeline, planner, rag, runner, tools_extra  # noqa: E402

ENV_INFO = env.load()   # 启动时读 .env（不覆盖已存在的环境变量）
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


def _jsonable(obj):
    """把不可序列化的内容（函数等）降级成字符串，保证 /api/run 永不因序列化失败。"""
    try:
        json.dumps(obj, ensure_ascii=False)
        return obj
    except TypeError:
        if isinstance(obj, (list, tuple)):
            return [_jsonable(x) for x in obj]
        if isinstance(obj, dict):
            return {str(k): _jsonable(v) for k, v in obj.items()}
        return str(obj)


# ------------------------------------------------------------
# 只读视图：前端各页面直接取，不跑 Agent，保证秒开
# ------------------------------------------------------------

ROW_FIELDS = ("kol_id", "handle", "platform", "category", "content_category",
              "followers", "price_band", "engagement_rate", "viral_rate",
              "comment_intent", "post_stability", "exposure_30d", "orders_30d",
              "aov", "quote", "fulfill_rate", "repurchase_rate",
              "past_collab_footcare", "D1", "D2", "D3", "D4", "total", "tier",
              "cvr", "uv_rate", "gmv", "cpm")


def scored_rows(budget=8000.0, platform=None, band=None, min_followers=0, top_n=8):
    """候选池 + 四维评分 + 预算可行性，一次性给到前端。"""
    search = core.search_candidates(platform=platform or None,
                                    price_band=band or None,
                                    min_followers=int(min_followers or 0),
                                    limit=300)
    rows = search.get("candidates", [])
    scored = core.score_candidates(rows)
    all_rows = scored.get("rows", [])
    alloc = core.allocate_budget([dict(r) for r in all_rows], budget, top_n=top_n)

    out = [{k: r.get(k) for k in ROW_FIELDS} for r in all_rows]
    total_score = round(sum(r["total"] for r in all_rows) / len(all_rows), 1) if all_rows else 0
    high = sum(1 for r in all_rows if r["tier"] in ("S", "A"))
    tiers = scored.get("tier_count", {})
    est = sum(p["quote"] for p in alloc.get("plan", [])) if alloc.get("feasible") else 0

    return {
        "total": scored.get("scored", 0),
        "platform_matched": search.get("matched", 0),
        "avg_score": total_score,
        "high_tier": high,
        "tier_count": tiers,
        "distribution": [
            {"tier": t, "count": tiers.get(t, 0),
             "ratio": round(tiers.get(t, 0) / len(all_rows), 3) if all_rows else 0}
            for t in ("S", "A", "B", "C")
        ],
        "estimated_spend": round(est, 0),
        "budget": budget,
        "allocation": alloc,
        "rows": out,
        "note": "分数为候选池内相对排序（百分位归一化），换一批候选分数会变",
    }


def _read_json_file(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def trend_series(days=14):
    """按日聚合投放执行数据，供工作台折线图。"""
    from collections import defaultdict
    agg = defaultdict(lambda: {"impressions": 0.0, "clicks": 0.0, "orders": 0.0,
                               "spend": 0.0, "gmv": 0.0})
    for r in datasource.load("campaign"):
        d = (r.get("dt") or "").strip()
        if not d:
            continue
        a = agg[d]
        for k in a:
            try:
                a[k] += float(r.get(k) or 0)
            except (TypeError, ValueError):
                pass
    dates = sorted(agg)[-days:]
    series = {k: [round(agg[d][k], 2) for d in dates] for k in
              ("impressions", "clicks", "orders", "spend", "gmv")}
    imp = sum(series["impressions"]) or 1
    clk = sum(series["clicks"]) or 1
    orders = sum(series["orders"])
    spend = sum(series["spend"]) or 1
    gmv = sum(series["gmv"])
    return {
        "days": len(dates),
        "dates": dates,
        "series": series,
        "totals": {
            "impressions": round(sum(series["impressions"])),
            "clicks": round(sum(series["clicks"])),
            "orders": round(orders),
            "spend": round(spend),
            "gmv": round(gmv),
            "roi": round(gmv / spend, 2),
            "ctr": round(clk / imp * 100, 2),
            "cvr": round(orders / clk * 100, 2),
        },
    }


def recent_tasks(limit=12):
    """最近任务 = traces 目录里的运行记录，按时间倒序。"""
    tdir = os.path.join(ROOT, "traces")
    items = []
    if not os.path.isdir(tdir):
        return {"items": []}
    files = [os.path.join(tdir, f) for f in os.listdir(tdir) if f.endswith(".json")]
    files.sort(key=os.path.getmtime, reverse=True)
    for p in files[:limit]:
        try:
            rec = _read_json_file(p)
        except Exception:
            continue
        stem = os.path.basename(p)[:-5]
        stamp = stem.split("-")
        ts = f"{stamp[0][:4]}-{stamp[0][4:6]}-{stamp[0][6:8]} {stamp[1][:2]}:{stamp[1][2:4]}:{stamp[1][4:6]}" \
            if len(stamp) >= 2 and len(stamp[0]) == 8 else stem
        final = (rec.get("final") or "").strip()
        first_line = next((ln.strip("# ").strip() for ln in final.splitlines()
                           if ln.strip().startswith("#")), "")
        items.append({
            "id": stem,
            "goal": rec.get("goal") or "",
            "planner": rec.get("planner") or "",
            "steps": rec.get("steps") or 0,
            "elapsed_ms": rec.get("elapsed_ms") or 0,
            "status": "completed" if final else "failed",
            "warnings": rec.get("warnings") or [],
            "title": first_line[:40],
            "final_head": final[:200],
            "ts": ts,
            "mtime": os.path.getmtime(p),
        })
    return {"items": items}


def outbox_reports(limit=10):
    odir = os.path.join(ROOT, "outbox")
    items = []
    if not os.path.isdir(odir):
        return {"items": []}
    files = [os.path.join(odir, f) for f in os.listdir(odir) if f.endswith(".md")]
    files.sort(key=os.path.getmtime, reverse=True)
    for p in files[:limit]:
        try:
            head = open(p, encoding="utf-8").readline().strip().lstrip("# ").strip()
        except Exception:
            head = os.path.basename(p)
        items.append({
            "file": os.path.basename(p),
            "title": head or os.path.basename(p),
            "size": os.path.getsize(p),
            "ts": os.path.getmtime(p),
        })
    return {"items": items}


def strategy_brief(goal="起量"):
    """商品销售结构 → 投放简报（主推渠道 / 配比 / 价格带 / 内容方向）。"""
    stats = parse_product_sales()
    if stats.get("error"):
        return {"error": stats["error"]}
    brief = core.build_brief(stats, goal=goal)
    brief["channel"] = stats.get("渠道销量结构", {})
    brief["aov"] = stats.get("估算客单价")
    brief["aov_conf"] = stats.get("客单价_置信度")
    brief["creators"] = stats.get("达人效率", {})
    return brief


def list_queues(limit=10):
    odir = os.path.join(ROOT, "outbox")
    items = []
    if not os.path.isdir(odir):
        return {"items": []}
    files = [os.path.join(odir, f) for f in os.listdir(odir)
             if f.startswith("outreach_queue_") and f.endswith(".json")]
    files.sort(key=os.path.getmtime, reverse=True)
    for p in files[:limit]:
        try:
            data = _read_json_file(p)
            count = len(data) if isinstance(data, list) else len(data.get("items", []))
        except Exception:
            count = 0
        items.append({"file": os.path.basename(p), "count": count,
                      "ts": os.path.getmtime(p), "size": os.path.getsize(p)})
    return {"items": items}


def read_queue(name):
    name = os.path.basename(name)
    if not (name.startswith("outreach_queue_") and name.endswith(".json")):
        return None
    fp = os.path.join(ROOT, "outbox", name)
    if not os.path.exists(fp):
        return None
    data = _read_json_file(fp)
    return {"file": name, "items": data if isinstance(data, list) else data.get("items", [])}


def read_task(task_id):
    tid = os.path.basename(task_id)
    if not re.fullmatch(r"[0-9]{8}-[0-9]{6}-[a-z]+", tid):
        return None
    fp = os.path.join(ROOT, "traces", tid + ".json")
    if not os.path.exists(fp):
        return None
    rec = _read_json_file(fp)
    rec["id"] = tid
    return rec


def run_agent(goal, budget, planner_name):
    # auto 必须解析成「有 key 就用模型」，否则默认永远走规则基线
    if planner_name == "auto":
        planner_name = "llm" if llm.available() else "rule"
    use_llm = planner_name == "llm" and llm.available()
    p = (planner.LLMPlanner() if use_llm
         else planner.RulePlanner(budget=budget))
    agent = runner.Agent(p, trace_dir=os.path.join(ROOT, "traces"))
    rec = agent.run(goal)

    # 暴露 agent 的思考过程与用量（plan 只取纯文本版，避免把函数塞进 JSON）
    rec["agent_meta"] = {
        "planner": getattr(p, "name", "?"),
        "model": llm._model() if use_llm else None,
        "plan": _jsonable(getattr(p, "plan_text", None) or getattr(p, "plan", None)),
        "tokens": getattr(p, "tokens", 0),
        "steps": rec.get("steps"),
        "llm_available": llm.available(),
        "env_loaded": ENV_INFO.get("loaded", 0),
    }

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

        if path == "/api/candidates":
            try:
                b = float(qs.get("budget", ["8000"])[0])
            except ValueError:
                b = 8000.0
            try:
                return self._json(scored_rows(
                    b,
                    platform=qs.get("platform", [""])[0],
                    band=qs.get("band", [""])[0],
                    min_followers=qs.get("min_followers", ["0"])[0],
                    top_n=int(qs.get("top_n", ["8"])[0])))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        if path == "/api/knowledge/search":
            q = qs.get("q", [""])[0]
            try:
                k = int(qs.get("k", ["3"])[0])
            except ValueError:
                k = 3
            if not q.strip():
                return self._json({"error": "缺少 q"}, 400)
            return self._json({"query": q, "hits": rag.search(q, k)})

        if path == "/api/knowledge/docs":
            return self._json({"docs": rag.list_docs()})

        if path == "/api/strategy":
            try:
                return self._json(strategy_brief(qs.get("goal", ["起量"])[0]))
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        if path == "/api/queues":
            return self._json(list_queues())

        if path.startswith("/api/queues/"):
            q = read_queue(urllib.parse.unquote(path[len("/api/queues/"):]))
            if q is None:
                return self._json({"error": "not found"}, 404)
            return self._json(q)

        if path.startswith("/api/tasks/"):
            rec = read_task(urllib.parse.unquote(path[len("/api/tasks/"):]))
            if rec is None:
                return self._json({"error": "not found"}, 404)
            return self._json(rec)

        if path == "/api/trend":
            try:
                days = int(qs.get("days", ["14"])[0])
            except ValueError:
                days = 14
            return self._json(trend_series(days))

        if path == "/api/tasks":
            try:
                limit = int(qs.get("limit", ["12"])[0])
            except ValueError:
                limit = 12
            return self._json(recent_tasks(limit))

        if path == "/api/content/samples":
            samples = datasource.load("content_samples")
            for s in samples:
                s["length"] = len("".join(s.get("body", "").split()))
                s["compliance"] = tools_extra.compliance_check(s.get("body", ""))
            return self._json({"samples": samples,
                               "platforms": list(tools_extra.LIMIT.keys()),
                               "limits": tools_extra.LIMIT})

        if path == "/api/funnel":
            kid = qs.get("kol_id", [""])[0]
            if not kid:
                return self._json({"error": "缺少 kol_id"}, 400)
            return self._json(tools_extra.diagnose_funnel(kid))

        if path == "/api/reports":
            return self._json(outbox_reports())

        if path.startswith("/api/reports/"):
            name = os.path.basename(urllib.parse.unquote(path[len("/api/reports/"):]))
            fp = os.path.join(ROOT, "outbox", name)
            if not name.endswith(".md") or not os.path.exists(fp):
                return self._json({"error": "not found"}, 404)
            with open(fp, encoding="utf-8") as f:
                return self._send(200, f.read(), "text/markdown; charset=utf-8")

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

        if path == "/api/llm/status":
            u = llm.usage_summary()
            return self._json({
                "available": llm.available(),
                "model": llm._model(),
                "base_url": llm._base(),
                "env_file": ENV_INFO.get("exists"),
                "env_loaded": ENV_INFO.get("loaded", 0),
                "usage": u,
            })

        if path == "/api/datasource":
            return self._json(datasource.describe())

        if path == "/api/export":
            ids = {x for x in qs.get("ids", [""])[0].split(",") if x}
            try:
                b = float(qs.get("budget", ["8000"])[0])
            except ValueError:
                b = 8000.0
            data = scored_rows(b)
            rows = [r for r in data["rows"] if not ids or r["kol_id"] in ids]
            if not rows:
                return self._json({"error": "没有可导出的达人"}, 400)
            head = "kol_id,handle,platform,tier,score,D1,D2,D3,D4,quote,followers"
            lines = [head] + [
                f"{r['kol_id']},{r['handle']},{r['platform']},{r['tier']},{r['total']},"
                f"{r['D1']},{r['D2']},{r['D3']},{r['D4']},{r['quote']},{r['followers']}"
                for r in rows]
            return self._send(200, "\ufeff" + "\n".join(lines), "text/csv; charset=utf-8")

        return self._json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path not in ("/api/run", "/api/notify", "/api/pipeline", "/api/llm/test",
                               "/api/content/rewrite", "/api/compliance"):
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

        if parsed.path == "/api/llm/test":
            if not llm.available():
                return self._json({"ok": False, "error": "未配置 DEEPSEEK_API_KEY（可写入项目根目录 .env）"}, 400)
            import time as _t
            t0 = _t.time()
            try:
                msg = llm.chat([{"role": "user", "content": "只回两个字：可用"}],
                               temperature=0, max_tokens=16)
                return self._json({"ok": True, "model": llm._model(),
                                   "reply": (msg.get("content") or "").strip(),
                                   "latency_ms": int((_t.time() - t0) * 1000),
                                   "usage": llm.last_usage})
            except Exception as e:
                return self._json({"ok": False, "error": f"{type(e).__name__}: {e}"}, 502)

        if parsed.path == "/api/pipeline":
            text = payload.get("text") or ""
            if not text.strip():
                return self._json({"error": "text 为空：请粘贴群消息或回调内容"}, 400)
            try:
                res = pipeline.run_pipeline(
                    [text],
                    min_tier=payload.get("min_tier", "A"),
                    write=bool(payload.get("write", True)),
                    push=bool(payload.get("push", False)))
                if res["outreach_queue"]:
                    res["queue_path"] = pipeline.save_queue(res["outreach_queue"])
                return self._json(res)
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

        if parsed.path == "/api/compliance":
            text = (payload.get("text") or "").strip()
            if not text:
                return self._json({"error": "缺少 text"}, 400)
            res = tools_extra.compliance_check(text)
            res["length"] = len("".join(text.split()))
            res["suggestions"] = ([f"命中「{c}」：{', '.join(sorted({h['word'] for h in res['hits'] if h['category'] == c}))}"
                                   for c in res["categories"]] if res["hits"] else ["未发现违规词，仍需人工终审"])
            return self._json(res)

        if parsed.path == "/api/content/rewrite":
            sample_id = (payload.get("sample_id") or "").strip()
            if not sample_id:
                return self._json({"error": "缺少 sample_id"}, 400)
            samples = datasource.load("content_samples")
            src = next((s for s in samples if s["id"] == sample_id), None)
            if not src:
                return self._json({"error": f"找不到样本 {sample_id}"}, 404)
            platforms = [p for p in (payload.get("platforms") or list(tools_extra.LIMIT.keys()))
                         if p in tools_extra.LIMIT][:3] or ["小红书"]
            product = (payload.get("product") or "指压板").strip()
            try:
                results = [tools_extra.rewrite_content(sample_id=sample_id, platform=p, product=product)
                           for p in platforms]
            except Exception as e:
                return self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            return self._json({"source": src, "results": results, "product": product,
                               "platforms": platforms})

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
