#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具注册表：给模型看的 schema 与真正执行的 handler 在这里对齐。

约定：能算出确定结果的工具（评分、ROI、异常判定）**不允许模型改数**，
模型只能决定调用顺序与参数。
"""

from . import core, tools_extra


class Ctx:
    """一次任务内的共享状态。工具之间靠它传递中间结果。"""

    def __init__(self):
        self.stats = {}
        self.brief = {}
        self.search = {}
        self.scored = {}
        self.allocation = {}
        self.monitor = {}
        self.review = {}
        self.reviews = []
        self.rewrites = []
        self.funnels = []
        self.artifacts = []


# ---------- handlers ----------

def h_parse(ctx, path=None):
    return core.parse_product_sales(path)


def h_build_brief(ctx, goal="起量"):
    return core.build_brief(ctx.stats, goal=goal)


def h_search(ctx, **kw):
    return core.search_candidates(**kw)


def h_score(ctx, **kw):
    return core.score_candidates(ctx.search.get("candidates", []), **kw)


def h_allocate(ctx, budget, top_n=8):
    return core.allocate_budget(ctx.scored.get("rows", []), budget, top_n=top_n)


def h_brief(ctx, kol_ids):
    return tools_extra.draft_collab_brief(kol_ids)


def h_negotiate(ctx, kol_ids):
    return tools_extra.negotiation_advice(kol_ids)


def h_rewrite(ctx, sample_id=None, text=None, platform="小红书"):
    return tools_extra.rewrite_content(sample_id=sample_id, text=text, platform=platform)


def h_compliance(ctx, text):
    return tools_extra.compliance_check(text)


def h_review(ctx, group_by="content_type"):
    return tools_extra.review_campaign(group_by=group_by)


def h_funnel(ctx, kol_id):
    return tools_extra.diagnose_funnel(kol_id)


def h_monitor(ctx, recent=3, baseline=7):
    return tools_extra.monitor_scan(recent=recent, baseline=baseline)


# ---------- specs ----------

SPECS = [
    {"name": "parse_product_sales", "handler": h_parse,
     "description": "解析商品销售分布（区间值自动取中值），返回渠道结构、达人效率、客单价置信度。",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string", "description": "销售分布文件路径，省略用样例"}}, "required": []}},

    {"name": "build_brief", "handler": h_build_brief,
     "description": "由销售结构生成投放简报：主推打法、达人类型配比、价格带、内容红线。",
     "parameters": {"type": "object", "properties": {
         "goal": {"type": "string", "description": "投放目标"}}, "required": []}},

    {"name": "search_candidates", "handler": h_search,
     "description": "按平台/价格带/粉丝量/报价/是否做过足部品类检索候选达人。",
     "parameters": {"type": "object", "properties": {
         "platform": {"type": "string"}, "price_band": {"type": "string"},
         "min_followers": {"type": "integer"}, "max_quote": {"type": "number"},
         "require_footcare": {"type": "boolean"}}, "required": []}},

    {"name": "score_candidates", "handler": h_score,
     "description": "四维评分（匹配30/内容25/转化30/成本15），输出 S/A/B/C 分层。",
     "parameters": {"type": "object", "properties": {
         "price_band": {"type": "string"}, "require_footcare": {"type": "boolean"}}, "required": []}},

    {"name": "allocate_budget", "handler": h_allocate,
     "description": "预算内按性价比选人。预算不足会拒绝并给最低要求，不会硬凑。",
     "parameters": {"type": "object", "properties": {
         "budget": {"type": "number"}, "top_n": {"type": "integer"}},
         "required": ["budget"]}},

    {"name": "draft_collab_brief", "handler": h_brief,
     "description": "为指定达人生成合作 brief（含压价区间、必现要素、禁止事项、交付要求）。",
     "parameters": {"type": "object", "properties": {
         "kol_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["kol_ids"]}},

    {"name": "negotiation_advice", "handler": h_negotiate,
     "description": "报价谈判建议：对比同池 CPM 中位数，给出压价目标或换人建议。",
     "parameters": {"type": "object", "properties": {
         "kol_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["kol_ids"]}},

    {"name": "rewrite_content", "handler": h_rewrite,
     "description": "把一条不合格种草稿改写为可投放版本，并按平台控制字数。会给出改动理由与遗留风险。",
     "parameters": {"type": "object", "properties": {
         "sample_id": {"type": "string", "description": "data/content_samples.json 中的 id"},
         "text": {"type": "string"}, "platform": {"type": "string"}}, "required": []}},

    {"name": "compliance_check", "handler": h_compliance,
     "description": "确定性合规扫描：医疗功效、绝对化、替代医疗、硬引导、疗效时间承诺。",
     "parameters": {"type": "object", "properties": {
         "text": {"type": "string"}}, "required": ["text"]}},

    {"name": "review_campaign", "handler": h_review,
     "description": "投放复盘：按内容类型/达人层级聚合 ROI、CTR、CVR、CPM，指出最好与最差。",
     "parameters": {"type": "object", "properties": {
         "group_by": {"type": "string", "enum": ["content_type", "tier", "kol_id"]}}, "required": []}},

    {"name": "diagnose_funnel", "handler": h_funnel,
     "description": "单达人漏斗定位：把变化拆到曝光/点击率/转化率/客单价，指出主因与动作。",
     "parameters": {"type": "object", "properties": {
         "kol_id": {"type": "string"}}, "required": ["kol_id"]}},

    {"name": "monitor_scan", "handler": h_monitor,
     "description": "投放中滚动监测：近 N 天 vs 前 M 天，命中阈值即告警（P0/P1）。",
     "parameters": {"type": "object", "properties": {
         "recent": {"type": "integer"}, "baseline": {"type": "integer"}}, "required": []}},
]

BY_NAME = {s["name"]: s for s in SPECS}

# 给模型看的精简 schema（不含 handler）
SCHEMAS = [{k: v for k, v in s.items() if k != "handler"} for s in SPECS]

# 需要人工确认的高风险工具：模型调用后要标注「待人工复核」
NEEDS_REVIEW = {"draft_collab_brief", "rewrite_content", "allocate_budget"}


def call(name, ctx, args):
    spec = BY_NAME.get(name)
    if not spec:
        return {"error": f"未知工具 {name}"}
    try:
        return spec["handler"](ctx, **(args or {}))
    except TypeError as e:
        # 参数不对：把错误原样返回，让规划器自己修
        return {"error": f"参数不合法：{e}", "accepted": list(
            spec["parameters"].get("properties", {}).keys())}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}
