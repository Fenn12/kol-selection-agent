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
# LLM 规划器（真正的 agent：先规划，再调工具，最后自查）
# ------------------------------------------------------------

PLAN_PROMPT = """先别动手。用 3–6 步写一个执行计划，告诉我你打算按什么顺序做、每步要拿到什么。

输出 JSON：{"plan": ["步骤1", "步骤2"], "missing": ["还缺什么信息"]}
只是计划，不要给答案。"""

REFLECT_PROMPT = """停一下，自查再回答：
1. 你结论里的每个数字，是否都能对应到某次工具返回？有没有自己估的？
2. 有没有该查但没查的？比如没看销售结构就直接给名单、没跑监测就说一切正常。
3. 有没有该拒绝而你没拒绝的？（预算不足、候选为空、数据缺失）
如果发现问题，继续调用工具补齐；如果确认无误，直接输出最终答案。"""

FINAL_FORMAT = """现在输出最终答案，读者是运营同学，不是我的内部记录。

要求：
1. 不要出现「上一轮」「修正说明」「我刚才说」「自查发现」这类自言自语——直接给结论。
2. 结构：判断依据（带数字）→ 结论/名单 → 风险与待人工确认项。
3. 关键数字标注来自哪个工具。
4. 如果不同工具的同一指标口径不一致，直接说明你采用哪一套、为什么。
5. 有做不到的地方就写明做不到，不要为了完整而凑。"""


class LLMPlanner:
    name = "llm"

    def __init__(self, max_steps=16, token_budget=150000,
                 obs_limit=2400, ctx_chars=40000):
        self.messages = [{"role": "system", "content": SYSTEM}]
        self.max_steps = max_steps
        self.token_budget = token_budget
        self.obs_limit = obs_limit        # 单条观察回灌上限（chars）
        self.ctx_chars = ctx_chars        # 触发上下文压缩的累计字符数
        self.plan = None
        self.tokens = 0
        self._n = 0
        self._repaired = set()
        self._reflected = False
        self._pending = []   # 同一条 assistant 消息里的多个 tool_call，逐个执行
        self._acted_after_reflect = False   # 自检后又补查过 → 结论需要重新成稿
        self._polished = False
        self._model = llm._model()

    @staticmethod
    def available():
        return llm.available()

    # ---------- 阶段一：先规划 ----------

    def _make_plan(self, goal):
        try:
            data = llm.chat_json([
                {"role": "system", "content": PLAN_PROMPT},
                {"role": "user", "content": f"任务：{goal}\n可用工具：{'、'.join(t['name'] for t in registry.SCHEMAS)}"}],
                temperature=0.2, max_tokens=500)
            self.tokens += llm.last_usage.get("total_tokens", 0)
            self.plan = data.get("plan") or []
            return data
        except llm.LLMError:
            return {}

    # ---------- 每步决策 ----------

    def next_action(self, goal, ctx):
        # 上一条 assistant 消息里还有没执行的 tool_call —— 先把手头的做完。
        # OpenAI/DeepSeek 要求每个 tool_call_id 都有对应 tool 回执，否则报 400。
        if self._pending:
            return self._pending.pop(0)

        self._n += 1

        if self._n == 1:
            planned = self._make_plan(goal)
            hint = ""
            if self.plan:
                hint = "\n\n你的计划：\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(self.plan, 1))
                if planned.get("missing"):
                    hint += f"\n已知缺失：{'、'.join(map(str, planned['missing']))}"
            self.messages.append({"role": "user", "content": goal + hint})

        # 触顶时不能只丢一句占位话 —— 让它基于已有事实把结论说完
        if self._n > self.max_steps or self.tokens > self.token_budget:
            return self._wrap_up(
                f"已达上限（步数 {self._n - 1}/{self.max_steps}，token {self.tokens}/{self.token_budget}），"
                "不要再调用工具，直接基于上面已有的工具返回给出结论，并说明哪些地方可能不完整。")

        self._compact()

        try:
            msg = llm.chat(self.messages, tools=registry.SCHEMAS, temperature=0.2, max_tokens=1500)
        except llm.LLMError as e:
            return {"final": f"模型调用失败：{e}"}
        self.tokens += llm.last_usage.get("total_tokens", 0)

        calls = msg.get("tool_calls") or []
        if not calls:
            # 想直接回答 —— 先让它自查一次
            if not self._reflected and self._n < self.max_steps:
                self._reflected = True
                self.messages.append(msg)
                self.messages.append({"role": "user", "content": REFLECT_PROMPT})
                return self.next_action(goal, ctx)
            draft = (msg.get("content") or "").strip() or "（模型未给出结论）"
            # 自检后补查过的话，草稿里常混着「上一轮我怎么说的」这类自言自语，重新成稿
            if self._acted_after_reflect:
                draft = self._polish(draft)
            return {"final": draft}

        self.messages.append(msg)
        thought = (msg.get("content") or "").strip()

        actions = []
        for i, c in enumerate(calls):
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            actions.append({
                "thought": thought if i == 0 else "（同一轮并行调用）",
                "tool": fn.get("name"),
                "args": args,
                # 少数兼容实现不返回 id，兜底造一个，保证 tool 回执能对上
                "call_id": c.get("id") or f"call_{self._n}_{i}",
            })

        if self._reflected:
            self._acted_after_reflect = True

        first, self._pending = actions[0], actions[1:]
        return first

    # ---------- 触顶收尾：把结论说完，而不是丢一句占位话 ----------

    def _wrap_up(self, notice):
        if getattr(self, "_wrapped", False):
            return {"final": f"{notice}\n（收尾调用未返回内容，以下为已有信息。）"}
        self._wrapped = True
        self.messages.append({"role": "user", "content": notice})
        try:
            # 不带 tools，强制它只能作答
            msg = llm.chat(self.messages, temperature=0.2, max_tokens=1500)
        except llm.LLMError as e:
            return {"final": f"{notice}\n模型调用失败：{e}"}
        self.tokens += llm.last_usage.get("total_tokens", 0)
        return {"final": (msg.get("content") or "").strip() or notice}

    # ---------- 终稿整理：去掉自言自语，按对外结构重排 ----------

    def _polish(self, draft):
        if self._polished:
            return draft
        self._polished = True
        self.messages.append({"role": "assistant", "content": draft})
        self.messages.append({"role": "user", "content": FINAL_FORMAT})
        try:
            msg = llm.chat(self.messages, temperature=0.2, max_tokens=1800)
        except llm.LLMError:
            return draft
        self.tokens += llm.last_usage.get("total_tokens", 0)
        return (msg.get("content") or "").strip() or draft

    # ---------- 上下文压缩：防止长任务把窗口撑爆 ----------

    def _compact(self):
        total = sum(len(str(m.get("content") or "")) for m in self.messages)
        if total <= self.ctx_chars:
            return
        # 最近 8 条保持完整，更早的 tool 回执压成摘要
        keep = 8
        idx = [i for i, m in enumerate(self.messages) if m.get("role") == "tool"]
        for i in idx[:-keep]:
            c = str(self.messages[i].get("content") or "")
            if len(c) > 300:
                self.messages[i]["content"] = c[:300] + "…（更早的回执已压缩，需要请重新调用该工具）"

    def observe(self, call_id, tool, obs):
        self.messages.append({"role": "tool", "tool_call_id": call_id,
                              "content": json.dumps(obs, ensure_ascii=False)[:self.obs_limit]})

    def repair(self, call_id, tool, err):
        if (call_id, tool) in self._repaired:
            return False
        self._repaired.add((call_id, tool))
        self.messages.append({"role": "tool", "tool_call_id": call_id,
                              "content": json.dumps({"error": err}, ensure_ascii=False)})
        # 同轮里没执行的调用也要补回执，否则下一次请求会因缺 tool 消息被拒
        self._flush_pending("因同轮调用报错而中止")
        self.messages.append({"role": "user", "content":
            f"上一次调用 {tool} 的参数不合法。可接受参数：{err.get('accepted')}。请修正后重试。"})
        return True

    def _flush_pending(self, note):
        for a in self._pending:
            self.messages.append({"role": "tool", "tool_call_id": a["call_id"],
                                  "content": json.dumps({"skipped": note}, ensure_ascii=False)})
        self._pending = []


# ------------------------------------------------------------
# 离线规则规划器
# ------------------------------------------------------------

INTENTS = {
    "筛选": ["筛选", "选人", "达人", "预算", "起量", "名单"],
    "合作": ["合作", "brief", "报价", "谈判", "邀约"],
    "复写": ["复写", "改写", "文案", "内容", "润色"],
    "复盘": ["复盘", "roi", "效果", "转化", "归因"],
    "监测": ["监测", "预警", "异常", "告警", "监控"],
    "日报": ["日报", "周报", "汇报", "报给", "总结一下"],
}


def detect(goal):
    g = goal.lower()
    hit = {k for k, ws in INTENTS.items() if any(w in g for w in ws)}
    if any(w in goal for w in ("全流程", "完整", "端到端", "一条龙")):
        return {"筛选", "合作", "复盘", "监测", "复写", "日报"}
    return hit or {"筛选"}


class RulePlanner:
    name = "rule"

    def __init__(self, budget=8000, top_n=8, sales_path=None, search_kwargs=None):
        self.budget = budget
        self.top_n = top_n
        self.sales_path = sales_path
        self.search_kwargs = search_kwargs or {}
        self.plan = None          # 内部执行序列（含取值函数，不可序列化）
        self.plan_text = None     # 对外展示的执行计划（纯文本）
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
                    ("draft_outreach_message", lambda c: {"kol_ids": _picked(c)[:3]}),
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
        if "日报" in want:
            steps += [
                ("monitor_scan", lambda c: {"recent": 3, "baseline": 7}),
                ("review_campaign", lambda c: {"group_by": "content_type"}),
                ("compose_daily_report", lambda c: {"budget": self.budget}),
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
            self.plan_text = [f"{t}：{_reason(t)}" for t, _ in self.plan]
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
        if getattr(ctx, "report", None):
            L.append(f"【日报】已生成 {len(ctx.report.get('markdown',''))} 字，P0 {ctx.report.get('p0')} / P1 {ctx.report.get('p1')}")
        if getattr(ctx, "outreach", None):
            L.append(f"【邀约】生成 {ctx.outreach.get('count')} 条话术（{ctx.outreach.get('messages',[{}])[0].get('mode') if ctx.outreach.get('messages') else '-'}）")
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
        "draft_outreach_message": "给入选达人生成可直接发的邀约话术",
        "compose_daily_report": "把今天的判断整理成能给主管看的日报",
    }.get(tool, "")
