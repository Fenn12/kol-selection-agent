#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KOL Operations MCP Server（stdio / JSON-RPC 2.0 / 换行分隔）。

暴露 3 个工具：
    search_knowledge  RAG 检索品牌语气、合规规则、选人方法
    score_candidates  候选池四维评分 + 预算分配
    monitor_scan      近 3 天 vs 前 7 天中位数告警

与 MCP 客户端握手示例见 scripts/mcp_smoke.py。
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent import core, rag, tools_extra  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "kol-ops-mcp", "version": "0.1.0"}


def tool_search_knowledge(args):
    query = str(args.get("query") or "").strip()
    if not query:
        raise ValueError("query 不能为空")
    top_k = max(1, min(int(args.get("top_k") or 3), 5))
    hits = rag.search(query, top_k=top_k)
    return {
        "query": query,
        "count": len(hits),
        "hits": [{"doc": h["doc"], "title": h["title"], "score": h["score"],
                  "text": h["text"][:260]} for h in hits],
    }


def tool_score_candidates(args):
    budget = float(args.get("budget") or 8000)
    top_n = max(1, min(int(args.get("top_n") or 8), 20))
    search = core.search_candidates(limit=300)
    scored = core.score_candidates(search.get("candidates", []))
    alloc = core.allocate_budget([dict(r) for r in scored.get("rows", [])], budget, top_n=top_n)
    return {
        "budget": budget,
        "scored": scored.get("scored"),
        "tier_count": scored.get("tier_count"),
        "picked": alloc.get("picked_count"),
        "spent": alloc.get("spent"),
        "remaining": alloc.get("remaining"),
        "note": alloc.get("note"),
        "picks": [{k: p.get(k) for k in ("kol_id", "handle", "platform", "tier", "score", "quote")}
                  for p in (alloc.get("plan") or [])[:5]],
    }


def tool_monitor_scan(args):
    res = tools_extra.monitor_scan()
    return {
        "alert_count": res.get("alert_count"),
        "by_severity": res.get("by_severity"),
        "window": res.get("window"),
        "alerts": [{k: a.get(k) for k in ("severity", "kol_id", "rule", "delta_pct", "hint")}
                   for a in (res.get("alerts") or [])[:5]],
    }


TOOLS = [
    {
        "name": "search_knowledge",
        "description": "RAG 检索本地知识库：品牌语气、内容合规规则、平台字数、达人评分与预算方法。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "检索问题，例如「小红书 极限词 长度」"},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 5, "default": 3},
            },
            "required": ["query"],
        },
    },
    {
        "name": "score_candidates",
        "description": "对候选达人做四维评分、分层，并在预算内按性价比分配。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "budget": {"type": "number", "description": "预算（元）", "default": 8000},
                "top_n": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            },
        },
    },
    {
        "name": "monitor_scan",
        "description": "扫描近 3 天投放异常（对比前 7 天中位数基线），返回 P0/P1 告警。",
        "inputSchema": {"type": "object", "properties": {}},
    },
]

HANDLERS = {
    "search_knowledge": tool_search_knowledge,
    "score_candidates": tool_score_candidates,
    "monitor_scan": tool_monitor_scan,
}


def reply(msg_id, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        out["error"] = error
    else:
        out["result"] = result
    sys.stdout.write(json.dumps(out, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle(req):
    method = req.get("method")
    msg_id = req.get("id")
    params = req.get("params") or {}

    if method == "initialize":
        reply(msg_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
        })
        return
    if method in ("notifications/initialized", "notifications/cancelled"):
        return
    if method == "ping":
        reply(msg_id, {})
        return
    if method == "tools/list":
        reply(msg_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if not handler:
            reply(msg_id, error={"code": -32602, "message": f"unknown tool: {name}"})
            return
        try:
            result = handler(args)
            reply(msg_id, {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                "isError": False,
            })
        except Exception as exc:  # 工具异常回给客户端，不中断 server
            reply(msg_id, {
                "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                "isError": True,
            })
        return

    if msg_id is not None:
        reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write("invalid json line\n")
            continue
        if isinstance(req, list):
            for item in req:
                handle(item)
        else:
            handle(req)


if __name__ == "__main__":
    main()
