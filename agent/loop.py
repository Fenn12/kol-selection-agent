#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent 主循环：规划 → 调工具 → 观察 → 再规划，直到给出结论。

两种规划器：
  LLMPlanner      —— 真正的 agent。用 OpenAI 兼容接口做 function calling。
  ScriptedPlanner —— 离线基线。没有 API key 时使用，保证仓库 clone 下来即可跑通，
                     同时作为 Agent 评测的对照组：如果 LLM 规划器跑不过它，说明
                     prompt 或工具设计有问题。

两者共用同一套工具与同一套「遇到异常就停」的护栏。
"""

import json
import os
import time
import urllib.request

from . import core

# ------------------------------------------------------------
# 护栏：工具返回这些信号时必须停下来，不许继续硬凑
# ------------------------------------------------------------

def guard(tool, obs):
    """返回一句终止说明；返回 None 表示可以继续。"""
    if not isinstance(obs, dict):
        return None
    if "error" in obs:
        return f"工具 {tool} 报错：{obs['error']}，无法继续。"
    if tool == "search_candidates" and obs.get("matched", 0) == 0:
        return ("候选池里没有符合条件的达人。不建议放宽标准硬凑名单——"
                "有效的做法是扩大平台范围、或把品类从「做过足部」放宽到「做过居家健身」。")
    if tool == "allocate_budget" and obs.get("feasible") is False:
        need = obs.get("min_budget_needed")
        extra = f"最低需要 {need:.0f} 元。" if isinstance(need, (int, float)) else ""
        return f"预算无法执行：{obs.get('reason')}。{extra}建议缩小名单或提高预算。"
    if tool == "parse_product_sales" and obs.get("销售额_中值", 0) == 0:
        return "销售数据为空或无法解析，无法生成简报。"
    return None


# ------------------------------------------------------------
# 规划器 1：离线脚本（基线）
# ------------------------------------------------------------

class ScriptedPlanner:
    """按固定顺序推进，但每一步的**参数**来自上一步的观察结果。

    这不是硬编码答案：预算、价格带、是否要求品类经验都由观察值决定，
    遇到异常同样会走 guard 分支。
    """

    name = "scripted"

    def __init__(self, budget=None, sales_path=None, search_kwargs=None):
        self.step = 0
        self.budget = budget
        self.sales_path = sales_path          # 可指向真实导出文件；None 用样例数据
        self.search_kwargs = search_kwargs or {}

    def next_action(self, task, state):
        self.step += 1
        s = self.step

        if s == 1:
            args = {"path": self.sales_path} if self.sales_path else {}
            return {"thought": "先把销售分布解析出来，看渠道结构和达人效率",
                    "tool": "parse_product_sales", "args": args}
        if s == 2:
            return {"thought": "根据渠道结构确定主推打法和价格带", "tool": "build_brief", "args": {"goal": task}}
        if s == 3:
            br = state.get("brief", {})
            band, conf = br.get("价格带定位"), br.get("客单价置信度", "中")
            # 客单价由两个区间中值相除得到，置信度低时不拿它当硬筛选条件，
            # 否则会把池子筛空——这是真实业务里很容易犯的错。
            kw = {"require_footcare": True}
            if conf == "高" and band:
                kw["price_band"] = band
            kw.update(self.search_kwargs)
            note = f"按价格带 {band} 检索" if "price_band" in kw else \
                   f"客单价置信度{conf}，不锁价格带，只要求足部品类经验"
            return {"thought": note, "tool": "search_candidates", "args": kw}
        if s == 4:
            band = state.get("brief", {}).get("价格带定位")
            return {"thought": "对候选池做四维评分并分层", "tool": "score_candidates",
                    "args": {"price_band": band, "require_footcare": True}}
        if s == 5:
            b = self.budget if self.budget is not None else 5000
            return {"thought": f"在 {b} 元预算内按性价比选人", "tool": "allocate_budget",
                    "args": {"budget": b, "top_n": 8}}
        return {"final": self._summarize(state)}

    @staticmethod
    def _summarize(state):
        st = state.get("stats", {})
        br = state.get("brief", {})
        sc = state.get("scored", {})
        al = state.get("allocation", {})
        if not al or not al.get("feasible"):
            return "没有得到可执行的投放名单。"
        lines = [
            f"商品侧：渠道结构为{br.get('主推渠道')}"
            f"（直播占 {st.get('渠道销量结构', {}).get('直播', {}).get('占比', 0):.0%}），"
            f"客单价约 {st.get('估算客单价')} 元（置信度{st.get('客单价_置信度', '中')}）。",
            f"达人侧：{sc.get('scored')} 人进入评分，S/A/B/C = "
            + " / ".join(str(sc.get("tier_count", {}).get(t, 0)) for t in "SABC") + "。",
            f"投放建议：预算 {al.get('budget')} 元，实投 {al.get('spent')} 元，"
            f"选 {al.get('picked_count')} 人，剩余 {al.get('remaining')} 元。",
            "名单：" + "、".join(f"{p['handle']}({p['tier']},{p['score']})" for p in al.get("plan", [])[:5]),
        ]
        return "\n".join(lines)


# ------------------------------------------------------------
# 规划器 2：LLM（真正的 agent）
# ------------------------------------------------------------

class LLMPlanner:
    name = "llm"

    def __init__(self, model=None, base_url=None, api_key=None, max_steps=8):
        self.key = api_key or os.getenv("OPENAI_API_KEY")
        self.base = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("MODEL") or "gpt-4o-mini"
        self.max_steps = max_steps
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self._steps = 0

    @staticmethod
    def available():
        return bool(os.getenv("OPENAI_API_KEY"))

    def _chat(self, messages, tools):
        payload = {"model": self.model, "messages": messages,
                   "tools": [{"type": "function", "function": t} for t in tools],
                   "tool_choice": "auto", "temperature": 0.2}
        req = urllib.request.Request(
            self.base + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read().decode("utf-8"))

    def next_action(self, task, state):
        self._steps += 1
        if self._steps == 1:
            self.messages.append({"role": "user", "content":
                f"{task}\n\n可用数据：data/product_sales.sample.csv、data/candidates.csv。"
                f"请调用工具完成筛选，最后给出名单与理由。"})
        if self._steps > self.max_steps:
            return {"final": "达到最大步数，停止并输出已知结论。"}

        try:
            data = self._chat(self.messages, core.TOOL_SPECS)
        except Exception as e:
            return {"final": f"模型调用失败：{e}"}

        msg = data["choices"][0]["message"]
        self.messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"final": msg.get("content") or "（模型未给出结论）"}

        c = calls[0]
        args = c["function"].get("arguments") or "{}"
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            args = {}
        return {"thought": msg.get("content") or "", "tool": c["function"]["name"],
                "args": args, "call_id": c["id"]}

    def observe(self, call_id, tool, obs):
        self.messages.append({"role": "tool", "tool_call_id": call_id,
                              "content": json.dumps(obs, ensure_ascii=False)[:4000]})


SYSTEM_PROMPT = """你是电商达人投放的筛选助手。工作方式：
1. 先看商品销售结构，再决定找哪类达人——不要跳过数据直接给名单。
2. 只使用工具返回的数据，禁止编造达人 id、报价或分数。
3. 数据不足或条件冲突时，直接说明缺什么，不要硬凑结论。
4. 最终回答要包含：渠道判断依据、入选名单（含 id 与理由）、预算使用情况。
5. 合规红线：不得建议使用医疗功效表述的达人内容。"""


# ------------------------------------------------------------
# Agent
# ------------------------------------------------------------

class Agent:
    def __init__(self, planner, trace_dir="traces"):
        self.planner = planner
        self.state = {}
        self.trace = []
        self.trace_dir = trace_dir

    def _call(self, tool, args):
        fn = getattr(core, tool, None)
        if fn is None:
            return {"error": f"未知工具 {tool}"}
        if tool == "build_brief":
            return fn(self.state.get("stats", {}), **args)
        if tool == "score_candidates":
            cands = self.state.get("search", {}).get("candidates", [])
            return fn(cands, **args)
        if tool == "allocate_budget":
            rows = self.state.get("scored", {}).get("rows", [])
            return fn(rows, **args)
        return fn(**args)

    def run(self, task, max_steps=10):
        t0 = time.time()
        final = None
        for n in range(1, max_steps + 1):
            action = self.planner.next_action(task, self.state)
            if "final" in action:
                final = action["final"]
                break

            tool, args = action["tool"], action.get("args", {})
            ts = time.time()
            obs = self._call(tool, args)
            dt = int((time.time() - ts) * 1000)

            self._stash(tool, obs)
            if hasattr(self.planner, "observe") and action.get("call_id"):
                self.planner.observe(action["call_id"], tool, obs)

            self.trace.append({"step": n, "thought": action.get("thought", ""), "tool": tool,
                               "args": args, "elapsed_ms": dt,
                               "observation": _shrink(obs)})

            stop = guard(tool, obs)
            if stop:
                final = stop
                break

        if final is None:
            final = "达到最大步数，未得出结论。"

        record = {"task": task, "planner": getattr(self.planner, "name", "unknown"),
                  "steps": len(self.trace), "elapsed_ms": int((time.time() - t0) * 1000),
                  "trace": self.trace, "final": final}
        self._save(record)
        return record

    def _stash(self, tool, obs):
        key = {"parse_product_sales": "stats", "build_brief": "brief",
               "search_candidates": "search", "score_candidates": "scored",
               "allocate_budget": "allocation"}.get(tool)
        if key and isinstance(obs, dict) and "error" not in obs:
            self.state[key] = obs

    def _save(self, record):
        os.makedirs(self.trace_dir, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S") + f"-{record['planner']}.json"
        with open(os.path.join(self.trace_dir, name), "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)


def _shrink(obs, limit=600):
    """trace 里只留关键字段，避免文件过大。"""
    if not isinstance(obs, dict):
        return obs
    if "rows" in obs:
        return {"scored": obs.get("scored"), "tier_count": obs.get("tier_count"),
                "top5": [{k: r[k] for k in ("kol_id", "tier", "total", "quote")} for r in obs["rows"][:5]]}
    if "candidates" in obs:
        return {"matched": obs.get("matched"),
                "top5": [{k: c[k] for k in ("kol_id", "followers", "quote")} for c in obs["candidates"][:5]]}
    if "plan" in obs:
        return obs
    s = json.dumps(obs, ensure_ascii=False)
    return json.loads(s) if len(s) <= limit * 4 else {"summary": s[:limit]}
