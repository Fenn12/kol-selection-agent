#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
工具层：数据解析、评分、预算分配。

所有工具都是纯函数，输入 dict、输出 dict，不依赖全局状态，
因此可以被 Agent 反复调用、也可以单独测试。
"""

import csv
import os
import re

from . import datasource

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


# ------------------------------------------------------------
# 区间解析：平台导出的数据常被区间化（"5000-1w"、"5%-10%"）
# 这是真实业务里最容易被忽略的一步，直接 float() 会崩。
# ------------------------------------------------------------

_UNIT = {"w": 10_000, "W": 10_000, "万": 10_000, "k": 1_000, "K": 1_000}


def _to_number(tok):
    # 数据库返回的是 int/float，CSV 返回的是字符串，两种都要能吃
    if isinstance(tok, (int, float)):
        return float(tok)
    tok = str(tok if tok is not None else "").strip().replace(",", "")
    if not tok:
        return 0.0
    m = re.match(r"^([\d.]+)\s*(w|W|万|k|K)?$", tok)
    if not m:
        return 0.0
    val = float(m.group(1))
    if m.group(2):
        val *= _UNIT[m.group(2)]
    return val


def parse_range(text):
    """把 "5000-1w" / "5%-10%" / "173" / "0.0" 解析成 (low, high, mid)。"""
    if text is None:
        return 0.0, 0.0, 0.0
    s = str(text).strip()
    if not s or s in ("-", "—"):
        return 0.0, 0.0, 0.0

    pct = s.endswith("%")
    s2 = s.replace("%", "").strip()

    # 区间：形如 a-b（单位可选 w/万/k）
    if re.match(r"^[\d.]+[wW万kK]?\s*-\s*[\d.]+[wW万kK]?$", s2):
        a, b = s2.split("-", 1)
        lo, hi = _to_number(a), _to_number(b)
    else:
        lo = hi = _to_number(s2)

    if pct:
        lo, hi = lo / 100.0, hi / 100.0
    return lo, hi, (lo + hi) / 2.0


# ------------------------------------------------------------
# 工具 1：解析商品销售分布
# ------------------------------------------------------------

def parse_product_sales(path=None):
    """读取商品销售分布（抖音电商罗盘「商品详情-销售分布」导出格式）。

    返回：总量、渠道结构、达人效率、转化率 —— 供后续生成简报使用。
    """
    if path:
        # 显式传了文件路径：直接读 CSV（不经过数据源，便于临时验证）
        if not os.path.exists(path):
            return {"error": f"文件不存在：{path}"}
        with open(path, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        src_name = os.path.basename(path)
    else:
        try:
            rows = datasource.load("product_sales")
            src_name = datasource.get().name
        except datasource.DataSourceError as e:
            return {"error": str(e)}
    if not rows:
        return {"error": "销售数据为空"}

    # 优先取「总计」行，没有则按日累加区间中值（近似）
    total = next((r for r in rows if str(r.get("日期", "")).strip() == "总计"), None)
    if total is None:
        return {"error": "未找到「总计」行，无法汇总"}

    sales_lo, sales_hi, sales_mid = parse_range(total.get("销售额"))
    qty_lo, qty_hi, qty_mid = parse_range(total.get("销量"))
    pv = _to_number(total.get("浏览量", "0"))
    cvr_lo, cvr_hi, cvr_mid = parse_range(total.get("转化率"))

    ch = {}
    for name, col in [("商品卡", "商品卡销量"), ("直播", "直播销量"), ("视频", "视频销量")]:
        _, _, mid = parse_range(total.get(col))
        ch[name] = mid
    ch_total = sum(ch.values()) or 1.0

    creators = {
        "总达人数": int(_to_number(total.get("带货达人", 0))),
        "视频达人": int(_to_number(total.get("视频带货达人", 0))),
        "直播达人": int(_to_number(total.get("直播带货达人", 0))),
        "带货视频": int(_to_number(total.get("带货视频", 0))),
        "带货直播": int(_to_number(total.get("带货直播", 0))),
    }

    # 客单价由两个区间中值相除得到，误差会被放大——必须标注置信度，
    # 不能拿一个假精确的数字去决定投放策略。
    aov = sales_mid / qty_mid if qty_mid else 0.0
    rel_width = ((sales_hi - sales_lo) / sales_mid if sales_mid else 1.0) + \
                ((qty_hi - qty_lo) / qty_mid if qty_mid else 1.0)
    aov_conf = "高" if rel_width < 0.6 else "中" if rel_width < 1.2 else "低"
    per_creator = qty_mid / creators["总达人数"] if creators["总达人数"] else 0.0
    per_video = qty_mid / creators["带货视频"] if creators["带货视频"] else 0.0

    return {
        "数据源": src_name,
        "区间提示": "平台导出为区间值，此处取区间中值近似，非精确数",
        "销售额_中值": round(sales_mid),
        "销售额_区间": [round(sales_lo), round(sales_hi)],
        "销量_中值": round(qty_mid),
        "浏览量": int(pv),
        "转化率_中值": round(cvr_mid, 4),
        "估算客单价": round(aov, 1),
        "客单价_置信度": aov_conf,
        "置信度说明": "客单价 = 销售额中值 / 销量中值，两个区间相除会放大误差；置信度低时应改用实际成交价",
        "渠道销量结构": {k: {"销量": round(v), "占比": round(v / ch_total, 3)} for k, v in ch.items()},
        "达人效率": {
            **creators,
            "人均产出_件": round(per_creator, 1),
            "单条视频产出_件": round(per_video, 1),
        },
    }


# ------------------------------------------------------------
# 工具 2：生成投放简报
# ------------------------------------------------------------

def build_brief(stats, goal="起量"):
    """根据销售结构推导投放策略：主推渠道、达人类型配比、目标画像。"""
    if "error" in stats:
        return stats

    ch = stats["渠道销量结构"]
    live = ch["直播"]["占比"]
    video = ch["视频"]["占比"]
    card = ch["商品卡"]["占比"]

    if live >= 0.45:
        main, mix = "达播为主", {"直播达人": 0.6, "短视频达人": 0.3, "商品卡承接": 0.1}
    elif video >= 0.35:
        main, mix = "短视频种草为主", {"短视频达人": 0.6, "直播达人": 0.25, "商品卡承接": 0.15}
    else:
        main, mix = "商品卡/搜索承接为主", {"短视频达人": 0.45, "直播达人": 0.25, "商品卡承接": 0.3}

    aov = stats["估算客单价"]
    conf = stats.get("客单价_置信度", "中")
    bands = ["低客单", "中客单", "中高客单", "高客单"]
    idx = 3 if aov >= 400 else 2 if aov >= 200 else 1 if aov >= 100 else 0
    band = bands[idx]
    # 置信度低时给出相邻备选，避免因为区间中点失真把池子筛空
    alt = [band] if conf == "高" else sorted({bands[max(idx - 1, 0)], band, bands[min(idx + 1, 3)]},
                                            key=lambda b: abs(bands.index(b) - idx))

    return {
        "投放目标": goal,
        "主推渠道": main,
        "达人类型配比": mix,
        "客单价": aov,
        "价格带定位": band,
        "价格带备选": alt,
        "客单价置信度": conf,
        "内容方向": ["居家场景实测", "痛点对比（久站/久坐）", "使用前后体感"],
        "需要回避": ["医疗功效表述", "替代治疗暗示"],
        "判断依据": {
            "直播占比": live, "视频占比": video, "商品卡占比": card,
            "人均产出_件": stats["达人效率"]["人均产出_件"],
            "客单价置信度": conf,
        },
    }


# ------------------------------------------------------------
# 工具 3：候选池检索
# ------------------------------------------------------------

def load_candidates(path=None):
    if path:
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    return datasource.load("candidates")


def search_candidates(platform=None, price_band=None, min_followers=0,
                      max_quote=None, require_footcare=False, limit=40):
    rows = load_candidates()
    out = []
    for r in rows:
        if platform and r["platform"] != platform:
            continue
        if price_band and r["price_band"] != price_band:
            continue
        if int(float(r["followers"])) < int(min_followers):
            continue
        if max_quote is not None and float(r["quote"]) > float(max_quote):
            continue
        if require_footcare and r["past_collab_footcare"] != "是":
            continue
        r2 = dict(r)
        for k in ("followers", "exposure_30d", "store_uv_30d", "orders_30d"):
            r2[k] = int(float(r2[k]))
        for k in ("aov", "quote"):
            r2[k] = float(r2[k])
        for k in ("engagement_rate", "viral_rate", "comment_intent", "post_stability",
                  "fulfill_rate", "repurchase_rate"):
            r2[k] = float(r2[k])
        out.append(r2)
    out.sort(key=lambda x: -x["followers"])
    return {"matched": len(out), "candidates": out[:limit]}


# ------------------------------------------------------------
# 工具 4：四维评分
# ------------------------------------------------------------

def _pct(v, arr):
    n = len(arr)
    if n <= 1:
        return 50.0
    below = sum(1 for x in arr if x < v)
    eq = sum(1 for x in arr if x == v)
    return round((below + (eq - 1) / 2) / (n - 1) * 100, 2)


def score_candidates(candidates, price_band=None, require_footcare=False):
    """四维加权：匹配度 30 / 内容 25 / 转化 30 / 成本 15，批内分位归一化。"""
    if not candidates:
        return {"scored": 0, "rows": [], "note": "候选池为空"}

    for c in candidates:
        c["cvr"] = c["orders_30d"] / c["store_uv_30d"] if c["store_uv_30d"] else 0.0
        c["uv_rate"] = c["store_uv_30d"] / c["exposure_30d"] if c["exposure_30d"] else 0.0
        c["gmv"] = c["orders_30d"] * c["aov"]
        c["cpm"] = c["quote"] / c["exposure_30d"] * 1000 if c["exposure_30d"] else 999
        c["quote_to_gmv"] = c["quote"] / c["gmv"] if c["gmv"] else 99

    def arr(f):
        return sorted(c[f] for c in candidates)

    a_eng, a_vir = arr("engagement_rate"), arr("viral_rate")
    a_ci, a_cvr, a_uv = arr("comment_intent"), arr("cvr"), arr("uv_rate")
    a_cpm, a_qg, a_ff = arr("cpm"), arr("quote_to_gmv"), arr("fulfill_rate")

    for c in candidates:
        match = 0.0
        match += 40 if (price_band and c["price_band"] == price_band) else 15
        match += 40 if c["past_collab_footcare"] == "是" else 10
        match += _pct(c["engagement_rate"], a_eng) * 0.2
        d1 = min(match, 100)

        d2 = (_pct(c["viral_rate"], a_vir) * 0.35 + _pct(c["engagement_rate"], a_eng) * 0.30 +
              _pct(c["comment_intent"], a_ci) * 0.20 + (100 - _pct(c["post_stability"], arr("post_stability"))) * 0.15)
        d3 = (_pct(c["cvr"], a_cvr) * 0.40 + _pct(c["uv_rate"], a_uv) * 0.30 +
              _pct(c["aov"], arr("aov")) * 0.20 + _pct(c["repurchase_rate"], arr("repurchase_rate")) * 0.10)
        d4 = (100 - _pct(c["cpm"], a_cpm)) * 0.40 + (100 - _pct(c["quote_to_gmv"], a_qg)) * 0.40 + \
             _pct(c["fulfill_rate"], a_ff) * 0.20

        total = d1 * 0.30 + d2 * 0.25 + d3 * 0.30 + d4 * 0.15
        c.update({"D1": round(d1, 1), "D2": round(d2, 1), "D3": round(d3, 1), "D4": round(d4, 1),
                  "total": round(total, 1), "tier": "S" if total >= 75 else "A" if total >= 62 else "B" if total >= 50 else "C"})

    rows = sorted(candidates, key=lambda x: -x["total"])
    return {"scored": len(rows), "tier_count": {t: sum(1 for r in rows if r["tier"] == t) for t in "SABC"},
            "rows": rows}


# ------------------------------------------------------------
# 工具 5：预算分配
# ------------------------------------------------------------

def allocate_budget(scored_rows, budget, top_n=8):
    """按「分数/成本」性价比贪心分配，预算不足时明确报告缺口，不硬凑。"""
    pool = [r for r in scored_rows if r["tier"] in ("S", "A", "B")]
    if not pool:
        return {"feasible": False, "reason": "无 B 层及以上达人，建议放宽筛选条件或降低分数门槛"}

    cheapest = min(r["quote"] for r in pool)
    if budget < cheapest:
        return {"feasible": False,
                "reason": f"预算 {budget} 低于最低报价 {cheapest:.0f}，无法执行",
                "min_budget_needed": cheapest}

    for r in pool:
        r["value_index"] = r["total"] / max(r["quote"], 1) * 1000

    pool.sort(key=lambda x: -x["value_index"])
    picked, spent = [], 0.0
    for r in pool:
        if len(picked) >= top_n:
            break
        if spent + r["quote"] <= budget:
            picked.append(r)
            spent += r["quote"]

    picked.sort(key=lambda r: (-r["total"], r["quote"]))
    remaining = budget - spent
    note = None
    if remaining > budget * 0.3:
        note = (f"预算只用掉 {spent / budget:.0%}，剩余 {remaining:.0f} 元。"
                f"原因：当前池子里 B 层以上且报价低的达人已被选完。"
                f"建议放宽到更高粉丝量级，或提高单人预算换 S/A 层。")
    return {
        "feasible": True,
        "note": note,
        "budget": budget,
        "spent": round(spent, 0),
        "remaining": round(budget - spent, 0),
        "picked_count": len(picked),
        "plan": [{ "kol_id": r["kol_id"], "handle": r["handle"], "platform": r["platform"],
                   "tier": r["tier"], "score": r["total"], "quote": r["quote"],
                   "value_index": round(r["value_index"], 2),
                   "reason": f"D1匹配{r['D1']} D3转化{r['D3']}，性价比 {round(r['value_index'],2)}" }
                 for r in picked],
    }


# ------------------------------------------------------------
# 工具注册表（给 LLM 看的就是这份 schema）
# ------------------------------------------------------------

TOOL_SPECS = [
    {"name": "parse_product_sales",
     "description": "解析商品销售分布表，返回销量/销售额/渠道结构/达人效率/转化率。区间值会自动取中值。",
     "parameters": {"type": "object", "properties": {"path": {"type": "string",
                    "description": "销售分布文件路径，省略则用样例数据"}}, "required": []}},
    {"name": "build_brief",
     "description": "根据销售统计生成投放简报：主推渠道、达人类型配比、价格带定位、内容方向与合规红线。",
     "parameters": {"type": "object", "properties": {
         "goal": {"type": "string", "description": "投放目标，如 起量 / 清库存 / 打爆品"}},
         "required": []}},
    {"name": "search_candidates",
     "description": "从候选达人池按平台/价格带/粉丝量/报价/是否做过足部品类筛选。",
     "parameters": {"type": "object", "properties": {
         "platform": {"type": "string", "enum": ["抖音", "小红书", "快手", "视频号"]},
         "price_band": {"type": "string", "enum": ["低客单", "中客单", "中高客单", "高客单"]},
         "min_followers": {"type": "integer"},
         "max_quote": {"type": "number"},
         "require_footcare": {"type": "boolean"}}, "required": []}},
    {"name": "score_candidates",
     "description": "对候选池做四维评分（匹配度/内容/转化/成本），返回 S/A/B/C 分层。",
     "parameters": {"type": "object", "properties": {
         "price_band": {"type": "string"}, "require_footcare": {"type": "boolean"}},
         "required": []}},
    {"name": "allocate_budget",
     "description": "按性价比在预算内选人，输出名单与剩余预算。预算不足会明确拒绝而不是硬凑。",
     "parameters": {"type": "object", "properties": {
         "budget": {"type": "number"}, "top_n": {"type": "integer"}},
         "required": ["budget"]}},
]
