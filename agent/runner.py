#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runner：执行规划器给出的动作，做护栏判断，落 trace。

护栏分两级：
    BLOCK  致命（报错 / 空池 / 预算不可行 / 数据缺失）→ 立即停，不继续
    WARN   可继续但要在结论里标注（合规未过 / 需人工复核）
"""

import json
import os
import time

from . import registry

BLOCK_KEYS = ("error",)


def guard_block(tool, obs):
    """返回终止说明或 None。"""
    if not isinstance(obs, dict):
        return None
    if any(k in obs for k in BLOCK_KEYS):
        return f"工具 {tool} 报错：{obs.get('error')}，流程终止。"

    if tool == "search_candidates" and obs.get("matched", 0) == 0:
        return ("候选池里没有符合条件的达人。不建议放宽标准硬凑名单——"
                "有效做法是扩大平台范围，或把品类从「做过足部」放宽到「做过居家健身」。")

    if tool == "allocate_budget" and obs.get("feasible") is False:
        need = obs.get("min_budget_needed")
        extra = f"最低需要 {need:.0f} 元。" if isinstance(need, (int, float)) else ""
        return f"预算无法执行：{obs.get('reason')}。{extra}建议缩小名单或提高预算。"

    if tool == "parse_product_sales" and obs.get("销售额_中值", 1) == 0:
        return "销售数据为空或无法解析，无法生成简报。"

    if tool in ("review_campaign", "monitor_scan") and not obs.get("rows") and not obs.get("alerts"):
        if tool == "review_campaign" and not obs.get("rows"):
            return "投放数据缺失，无法复盘。"

    return None


def guard_warn(tool, obs):
    """不阻断，但要进结论的风险提示。"""
    w = []
    if tool == "rewrite_content":
        after = obs.get("after_compliance") or {}
        if after and not after.get("pass", True):
            w.append(f"复写后仍有合规问题：{[h['word'] for h in after.get('hits', [])][:4]}")
        if obs.get("risk_flags"):
            w.append("需人工确认：" + "；".join(map(str, obs["risk_flags"][:3])))
    if tool in registry.NEEDS_REVIEW:
        w.append(f"{tool} 属于高风险产出，需人工复核后使用")
    if tool == "monitor_scan" and obs.get("alert_count", 0) == 0:
        w.append("本期未命中告警阈值（不等于没有风险，阈值可能过宽）")
    return w


class Agent:
    def __init__(self, planner, trace_dir="traces"):
        self.planner = planner
        self.ctx = registry.Ctx()
        self.trace = []
        self.warnings = []
        self.trace_dir = trace_dir

    def run(self, goal, max_steps=20):
        t0 = time.time()
        final, stopped = None, None

        for n in range(1, max_steps + 1):
            action = self.planner.next_action(goal, self.ctx)
            if "final" in action:
                final = action["final"]
                break

            tool, args = action["tool"], action.get("args") or {}
            ts = time.time()
            obs = registry.call(tool, self.ctx, args)
            dt = int((time.time() - ts) * 1000)

            # 参数错误 → 让规划器修一次
            if isinstance(obs, dict) and "参数不合法" in str(obs.get("error", "")):
                if hasattr(self.planner, "repair") and action.get("call_id"):
                    if self.planner.repair(action["call_id"], tool, obs):
                        self.trace.append({"step": n, "tool": tool, "args": args,
                                           "elapsed_ms": dt, "observation": obs,
                                           "flag": "ARG_ERROR_RETRY"})
                        continue

            self._stash(tool, obs)
            if hasattr(self.planner, "observe") and action.get("call_id"):
                self.planner.observe(action["call_id"], tool, obs)

            self.warnings += guard_warn(tool, obs)
            self.trace.append({"step": n, "thought": action.get("thought", ""), "tool": tool,
                               "args": args, "elapsed_ms": dt, "observation": _shrink(obs)})

            stopped = guard_block(tool, obs)
            if stopped:
                final = stopped
                break

        if final is None:
            final = "达到最大步数，未得出结论。"

        rec = {"goal": goal, "planner": getattr(self.planner, "name", "?"),
               "steps": len(self.trace), "elapsed_ms": int((time.time() - t0) * 1000),
               "stopped_early": bool(stopped), "warnings": self.warnings,
               "trace": self.trace, "final": final}
        self._save(rec)
        return rec

    # ---------- 内部 ----------

    def _stash(self, tool, obs):
        if not isinstance(obs, dict) or "error" in obs:
            return
        c = self.ctx
        if tool == "parse_product_sales":
            c.stats = obs
        elif tool == "build_brief":
            c.brief = obs
        elif tool == "search_candidates":
            c.search = obs
        elif tool == "score_candidates":
            c.scored = obs
        elif tool == "allocate_budget":
            c.allocation = obs
        elif tool == "monitor_scan":
            c.monitor = obs
        elif tool == "review_campaign":
            c.review = obs
            c.reviews.append(obs)
        elif tool == "rewrite_content":
            c.rewrites.append(obs)
        elif tool == "diagnose_funnel":
            if not obs.get("error"):
                c.funnels.append(obs)

    def _save(self, rec):
        os.makedirs(self.trace_dir, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S") + f"-{rec['planner']}.json"
        with open(os.path.join(self.trace_dir, name), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)


def _shrink(obs, limit=400):
    if not isinstance(obs, dict):
        return obs
    if "rows" in obs:
        return {"group_by": obs.get("group_by"), "overall": obs.get("overall"),
                "best": obs.get("best"), "worst": obs.get("worst"),
                "top3": obs["rows"][:3], "bottom1": obs["rows"][-1:]}
    if "alerts" in obs:
        return {"alert_count": obs.get("alert_count"), "by_severity": obs.get("by_severity"),
                "alerts": obs["alerts"][:4]}
    if "briefs" in obs:
        return {"count": obs.get("count"), "sample": obs["briefs"][0] if obs["briefs"] else None}
    if "plan" in obs:
        return obs
    s = json.dumps(obs, ensure_ascii=False)
    return obs if len(s) <= limit * 6 else {"summary": s[:limit]}
