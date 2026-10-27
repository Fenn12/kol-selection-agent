#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规划器：把「目标」翻译成工具调用序列。

LLMPlanner  真正的 agent：function calling + 参数纠错 + 自检
RulePlanner 离线基线：按关键词路由四类任务，用于无 key 环境与评测对照

两者共用 registry 的护栏与 trace 结构。
"""

import json
import os

from . import llm, registry

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

SYSTEM = """你是电商投放的运营助手，覆盖四件事：达人筛选与合作、内容复写、数据复盘、投放监测。

工作原则（违反会被判为不合格）：
1. 先看数据再给结论。涉及投放建议时，必须先拿到销售结构或投放数据。
2. 所有数字只能来自工具返回，禁止自己估算、禁止编造达人 id 或报价。
3. 结果不可行时直接说明（预算不足、候选为空、数据缺失），不要硬凑一个看似完整的方案。
4. 内容复写前先跑合规检查，复写后再跑一次，两次结果都要说明。
5. 最终回答结构：判断依据（带数字）→ 结论/名单 → 风险与待人工确认项。

工具选择建议：
- 要"选人"：parse_product_sales → build_brief → search_candidates → score_candidates → allocate_budget
- 要"合作"：拿到名单后 draft_collab_brief / negotiation_advice
- 要"复盘"：review_campaign，再对最差的用 diagnose_funnel
- 要"监测"：monitor_scan，再对 P0 告警用 diagnose_funnel
- 要"复写"：先 compliance_check 原文，再 rewrite_content，最后再 check 一次"""


# ------------------------------------------------------------
# LLM 规划器
# ------------------------------------------------------------

class LLMPlanner:
    name = "llm"

    def __init__(self, max_steps=14):
        self.max_steps = max_steps
        self.messages = [{"role": "system", "content": SYSTEM}]
        self._n = 0
        self._repaired = set()

    @staticmethod
    def available():
        return llm.available()

    def next_action(self, goal, ctx):
        self._n += 1
        if self._n == 1:
            self.messages.append({"role": "user", "content": goal})
        if self._n > self.max_steps:
            return {"final": "达到最大步数上限，基于已知信息给出阶段性结论（可能不完整）。"}

        try:
            msg = llm.chat(self.messages, tools=registry.SCHEMAS, temperature=0.2, max_tokens=1500)
        except llm.LLMError as e:
            return {"final": f"模型调用失败：{e}"}

        self.messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            return {"final": (msg.get("content") or "").strip() or "（模型未给出结论）"}

        c = calls[0]
        name = c["function"]["name"]
        raw = c["function"].get("arguments") or "{}"
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {}
        return {"thought": (msg.get("content") or "").strip(), "tool": name,
                "args": args, "call_id": c["id"]}

    def observe(self, call_id, tool, obs):
        self.messages.append({"role": "tool", "tool_call_id": call_id,
                              "content": json.dumps(obs, ensure_ascii=False)[:6000]})

    def repair(self, call_id, tool, err):
        """参数报错时把可接受的参数名告诉模型，允许重试一次。"""
        if (call_id, tool) in self._repaired:
            return False
        self._repaired.add((call_id, tool))
        self.messages.append({"role": "tool", "tool_call_id": call_id,
                              "content": json.dumps({"error": err}, ensure_ascii=False)})
        self.messages.append({"role": "user", "content":
            f"上一次调用 {tool} 的参数不合法。可接受参数：{err.get('accepted')}。请修正后重试。"})
        return True


# ------------------------------------------------------------
# 离线规则规划器
# ------------------------------------------------------------

INTENTS = {
    "筛选": ["筛选", "选人", "达人", "预算", "起量", "名单"],
    "合作": ["合作", "brief", "报价", "谈判", "邀约"],
    "复写": ["复写", "改写", "文案", "内容", "润色"],
    "复盘": ["复盘", "roi", "效果", "转化", "归因"],
    "监测": ["监测", "预警", "异常", "告警", "监控"],
}


def detect(goal):
    g = goal.lower()
    hit = {k for k, ws in INTENTS.items() if any(w in g for w in ws)}
    if any(w in goal for w in ("全流程", "完整", "端到端", "一条龙")):
        return {"筛选", "合作", "复盘", "监测", "复写"}
    return hit or {"筛选"}


class RulePlanner:
    name = "rule"

    def __init__(self, budget=8000, top_n=8, sales_path=None, search_kwargs=None):
        self.budget = budget
        self.top_n = top_n
        self.sales_path = sales_path
        self.search_kwargs = search_kwargs or {}
        self.plan = None
        self.i = 0

    def _build(self, goal):
        want = detect(goal)
        steps = []
        if "筛选" in want:
            steps += [
                ("parse_product_sales", lambda c: ({"path": self.sales_path} if self.sales_path else {})),
                ("build_brief", lambda c: {"goal": goal}),
                ("search_candidates", lambda c: {**{"require_footcare": True}, **self.search_kwargs}),
                ("score_candidates", lambda c: {}),
                ("allocate_budget", lambda c: {"budget": self.budget, "top_n": self.top_n}),
            ]
            if "合作" in want:
                steps += [
                    ("negotiation_advice", lambda c: {"kol_ids": _picked(c)[:5]}),
                    ("draft_collab_brief", lambda c: {"kol_ids": _picked(c)[:3]}),
                ]
        if "复盘" in want:
            steps += [
                ("review_campaign", lambda c: {"group_by": "content_type"}),
                ("review_campaign", lambda c: {"group_by": "kol_id"}),
                ("diagnose_funnel", lambda c: {"kol_id": _worst_kol(c)}),
            ]
        if "监测" in want:
            steps += [
                ("monitor_scan", lambda c: {"recent": 3, "baseline": 7}),
                ("diagnose_funnel", lambda c: {"kol_id": _first_p0(c)}),
            ]
        if "复写" in want:
            for sid in ("C1", "C2", "C3"):
                steps.append(("compliance_check",
                              lambda c, s=sid: {"text": _pre_text(s)}))
                steps.append(("rewrite_content",
                              lambda c, s=sid: {"sample_id": s, "platform": _plat(s)}))
        return steps

    def next_action(self, goal, ctx):
        if self.plan is None:
            self.plan = self._build(goal)
        if self.i >= len(self.plan):
            return {"final": self._summary(ctx, goal)}

        tool, argfn = self.plan[self.i]
        self.i += 1

        return {"thought": _reason(tool), "tool": tool, "args": argfn(ctx)}

    def _summary(self, ctx, goal):
        L = [f"目标：{goal}", ""]
        if ctx.stats:
            st = ctx.stats
            L.append(f"【商品】渠道结构 {ctx.brief.get('主推渠道', '-')}，"
                     f"直播占比 {st.get('渠道销量结构', {}).get('直播', {}).get('占比', 0):.0%}，"
                     f"客单价 {st.get('估算客单价')} 元（置信度{st.get('客单价_置信度', '中')}）")
        if ctx.allocation:
            a = ctx.allocation
            if a.get("feasible"):
                L.append(f"【选人】{a['picked_count']} 人，花费 {a['spent']:.0f}/{a['budget']:.0f} 元，"
                         f"剩余 {a['remaining']:.0f} 元")
                L.append("　　名单：" + "、".join(f"{p['handle']}({p['tier']},{p['score']})"
                                                for p in a["plan"][:6]))
            else:
                L.append(f"【选人】无法执行：{a.get('reason')}")
        if ctx.scored:
            tc = ctx.scored.get("tier_count", {})
            L.append(f"【评分】{ctx.scored.get('scored')} 人进入，S/A/B/C = "
                     + "/".join(str(tc.get(t, 0)) for t in "SABC"))
        if ctx.monitor:
            m = ctx.monitor
            L.append(f"【监测】扫描 {m['scanned_kols']} 人，告警 {m['alert_count']} 条"
                     f"（P0 {m['by_severity'].get('P0', 0)} / P1 {m['by_severity'].get('P1', 0)}）")
            for al in m["alerts"][:3]:
                L.append(f"　　· [{al['severity']}] {al['kol_id']} {al['rule']} "
                         f"{al['delta_pct']}% → {al['hint']}")
        if ctx.review:
            r = ctx.review
            L.append(f"【复盘】整体 ROI {r['overall']['roi']}，最好 {r['best']}，最差 {r['worst']}")
            for row in r["rows"][:3]:
                L.append(f"　　· {row['group']}: ROI {row['roi']} / CTR {row['ctr']}% / CVR {row['cvr']}%")
        if ctx.rewrites:
            L.append(f"【复写】完成 {len(ctx.rewrites)} 条")
            for w in ctx.rewrites:
                L.append(f"　　· {w['source_id']} 改前违规 {w['before_compliance']['hit_count']} 处 → "
                         f"改后 {w.get('after_compliance', {}).get('hit_count', '?')} 处，模式 {w.get('mode')}")
        if ctx.funnels:
            L.append("【漏斗】")
            for f in ctx.funnels:
                drv = f.get("main_driver", "未知")
                dev = f.get("deviation_pct", {})
                d = f"{dev[drv]}%" if drv in dev else "—"
                L.append(f"　　· {f['kol_id']} 主因 {drv}（{d}）→ {f.get('suggested_action', '')}")
        L.append("")
        L.append("注：以上数字均来自工具返回；内容类产出需人工终审后发布。")
        return "\n".join(L)


# ---------- 小工具 ----------

def _picked(ctx):
    a = ctx.allocation or {}
    return [p["kol_id"] for p in a.get("plan", [])]


def _worst_kol(ctx):
    r = ctx.review or {}
    rows = [x for x in r.get("rows", []) if x["group"].startswith("K")]
    return rows[-1]["group"] if rows else "K040"


def _first_p0(ctx):
    m = ctx.monitor or {}
    for al in m.get("alerts", []):
        if al["severity"] == "P0":
            return al["kol_id"]
    return "K040"


def _plat(sid):
    return {"C1": "小红书", "C2": "抖音", "C3": "视频号"}.get(sid, "小红书")


def _pre_text(sid):
    try:
        data = json.load(open(os.path.join(DATA_DIR, "content_samples.json"), encoding="utf-8"))
        return next(s["body"] for s in data if s["id"] == sid)
    except Exception:
        return ""


def _reason(tool):
    return {
        "parse_product_sales": "先看商品靠什么渠道卖出去，再决定找哪类达人",
        "build_brief": "由销售结构推导打法与价格带",
        "search_candidates": "按品类经验筛候选池",
        "score_candidates": "四维评分并分层",
        "allocate_budget": "预算内按性价比选人",
        "negotiation_advice": "对比同池 CPM 中位，判断要不要压价",
        "draft_collab_brief": "给入选达人生成合作 brief",
        "review_campaign": "聚合投放数据看 ROI 与效率",
        "diagnose_funnel": "定位掉在漏斗哪一环",
        "monitor_scan": "滚动比对近期与前基线，找异常",
        "compliance_check": "复写前先记录原文违规项",
    }.get(tool, "")
