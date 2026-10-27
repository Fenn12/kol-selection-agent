# -*- coding: utf-8 -*-
"""MCP stdio 客户端冒烟：initialize → tools/list → 3 个 tools/call。"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "mcp", "server.py")


class MCPClient:
    def __init__(self):
        self.proc = subprocess.Popen(
            [sys.executable, SERVER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", bufsize=1,
        )
        self.next_id = 1

    def send(self, payload):
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def request(self, method, params=None):
        req_id = self.next_id
        self.next_id += 1
        self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}})
        line = self.proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed stdout")
        return json.loads(line)

    def notify(self, method, params=None):
        self.send({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:
            pass


def main():
    c = MCPClient()
    transcript = []
    try:
        init = c.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "kol-smoke", "version": "0.1.0"},
        })
        transcript.append({"step": "initialize", "response": init})

        c.notify("notifications/initialized")
        info = (init.get("result") or {}).get("serverInfo") or {}

        listed = c.request("tools/list")
        tools = (listed.get("result") or {}).get("tools") or []
        transcript.append({"step": "tools/list", "tools": [t["name"] for t in tools]})

        calls = [
            ("search_knowledge", {"query": "小红书 极限词 字数", "top_k": 3}),
            ("score_candidates", {"budget": 8000, "top_n": 8}),
            ("monitor_scan", {}),
        ]
        for name, args in calls:
            resp = c.request("tools/call", {"name": name, "arguments": args})
            content = (resp.get("result") or {}).get("content") or []
            text = content[0]["text"] if content else ""
            payload = json.loads(text) if text.startswith("{") else {"raw": text}
            transcript.append({"step": "tools/call", "name": name, "result": payload})

        search = transcript[2]["result"]
        score = transcript[3]["result"]
        monitor = transcript[4]["result"]
        ok = (
            init.get("result", {}).get("protocolVersion") == "2024-11-05"
            and len(tools) == 3
            and search.get("count", 0) > 0
            and score.get("scored", 0) > 0
            and "alert_count" in monitor
        )
        summary = {
            "ok": ok,
            "server": info,
            "protocol_version": init.get("result", {}).get("protocolVersion"),
            "tools": [t["name"] for t in tools],
            "search_hits": search.get("count"),
            "search_top": (search.get("hits") or [{}])[0].get("doc"),
            "scored": score.get("scored"),
            "picked": score.get("picked"),
            "spent": score.get("spent"),
            "alerts": monitor.get("alert_count"),
        }
    finally:
        c.close()

    print(json.dumps({"summary": summary, "transcript": transcript}, ensure_ascii=False, indent=2))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
