#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
扩展工具：KOL 合作 / 内容复写 / 数据复盘 / 投放监测。

分工原则：
    能算的用代码（评分、ROI、异常判定）—— 结果可复现，模型不许改数
    要写的用模型（brief、复写）—— 有 key 走 LLM，无 key 走模板，接口一致
"""

import csv
import json
import os
import re
from collections import defaultdict

from . import llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


# ------------------------------------------------------------
# 通用读取
# ------------------------------------------------------------

def _read_csv(name):
    with open(os.path.join(DATA, name), encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------
# A. KOL 合作：brief 与谈判
# ------------------------------------------------------------

BRIEF_TEMPLATE = """# 合作 Brief｜{handle}（{kol_id}）

**合作形式**：{platform} 单条内容 + 授权二次剪辑
**参考报价**：{quote} 元　**建议区间**：{low}–{high} 元

## 一句话定位
{positioning}

## 必须出现
1. 具体使用场景（久坐 / 久站 / 居家），不要泛开场
2. 材质与尺寸的真实体感描述，不写参数表
3. 软性引导，不出现"点击购买""赶紧冲"

## 禁止出现
- 任何疾病、疗效、"疏通经络""改善睡眠"类表述
- "最""第一""国家级"等绝对化用语
- 与其他品牌对比贬损

## 交付要求
- 时长 30–60 秒，前 3 秒出现场景
- 成片前提供脚本大纲，我方 24 小时内反馈
- 保留原始素材 30 天，供二次剪辑"""


def draft_collab_brief(kol_ids, product="指压板"):
    """为指定达人生成合作 brief。有 key 用模型润色定位，无 key 用模板。"""
    cands = {c["kol_id"]: c for c in _read_csv("candidates.csv")}
    quotes = sorted(float(c["quote"]) for c in cands.values())
    median = quotes[len(quotes) // 2] if quotes else 0

    out = []
    for kid in kol_ids:
        c = cands.get(kid)
        if not c:
            out.append({"kol_id": kid, "error": "候选人池中无此 id"})
            continue
        q = float(c["quote"])
        low, high = round(q * 0.75), round(q * 0.95)     # 目标压到 75–95 折
        positioning = (f"{c['category']}方向，面向 {c['audience_age']} 岁、{c['audience_city']}人群，"
                       f"内容调性偏实测而非种草")

        if llm.available():
            try:
                positioning = llm.chat_text([
                    {"role": "system", "content": "你是达人合作 PM，写一句话人设定位，不超过 40 字，不要形容词堆砌。"},
                    {"role": "user", "content": f"达人：{c['handle']}，方向{c['category']}，"
                                                f"人群{c['audience_age']}岁/{c['audience_city']}，"
                                                f"粉丝{c['followers']}。产品：{product}。"}],
                    temperature=0.6, max_tokens=120)
            except llm.LLMError:
                pass  # 模型失败就退回模板，不阻塞主流程

        out.append({
            "kol_id": kid, "handle": c["handle"], "platform": c["platform"],
            "quote": q, "suggest_quote_range": [low, high],
            "peer_median_quote": median,
            "content": BRIEF_TEMPLATE.format(handle=c["handle"], kol_id=kid, platform=c["platform"],
                                             quote=int(q), low=low, high=high, positioning=positioning),
        })
    return {"briefs": out, "count": len(out)}


def negotiation_advice(kol_ids):
    """报价谈判建议：基于同池同类达人的 CPM 中位数与自身报价偏离度。"""
    cands = {c["kol_id"]: c for c in _read_csv("candidates.csv")}
    pool = list(cands.values())
    cpm = {}
    for c in pool:
        exp = _num(c["exposure_30d"])
        if exp > 0:
            cpm[c["kol_id"]] = float(c["quote"]) / exp * 1000
    if not cpm:
        return {"error": "缺少曝光数据，无法计算 CPM"}
    med = sorted(cpm.values())[len(cpm) // 2]

    rows = []
    for kid in kol_ids:
        c = cands.get(kid)
        if not c or kid not in cpm:
            continue
        v = cpm[kid]
        gap = (v - med) / med if med else 0
        if gap > 0.35:
            action, target = "报价偏高，建议压价或换人", round(float(c["quote"]) * (med / v) * 1.1)
        elif gap < -0.25:
            action, target = "报价显著低于均值，注意履约质量，可考虑加量", None
        else:
            action, target = "报价合理，可直接谈档期", None
        rows.append({"kol_id": kid, "handle": c["handle"], "quote": float(c["quote"]),
                     "cpm": round(v, 2), "pool_median_cpm": round(med, 2),
                     "gap_pct": round(gap * 100, 1), "action": action,
                     "suggest_target_quote": target})
    return {"pool_median_cpm": round(med, 2), "rows": rows}


# ------------------------------------------------------------
# B. 内容复写与合规
# ------------------------------------------------------------

BANNED = {
    "医疗功效": ["疏通经络", "改善睡眠", "治疗", "缓解", "祛", "根治", "穴位刺激", "比吃药"],
    "绝对化": ["最好", "第一", "唯一", "国家级", "顶级", "100%", "全网最低"],
    "替代医疗": ["替代药物", "无需就医", "比吃药强", "包治"],
    "硬引导": ["点击购买", "赶紧冲", "链接放评论区", "闭眼入"],
}

REWRITE_SYSTEM = """你是消费品内容编辑，做「合规化改写」而不是简单润色。

任务：把一条不合格的种草稿改写成可投放版本。
硬性要求：
1. 删除一切疾病、疗效、替代药物的表述，改为可观察的使用体感
2. 开头两行必须落在具体场景或具体痛点，禁用「姐妹们」「谁懂啊」这类泛开场
3. 卖点按「痛点 → 机制 → 体感」推进，不写参数表
4. 结尾只能软引导，不出现购买指令
5. 不同平台长度不同：小红书 300-500 字，抖音口播 80-150 字，视频号 120-200 字

输出 JSON：{"title": "...", "body": "...", "changes": ["改了什么，为什么"], "risk_flags": ["仍需人工确认的点"]}"""


def compliance_check(text):
    """确定性合规扫描。不调模型——这类判定必须可复现。"""
    hits = []
    for cat, words in BANNED.items():
        for w in words:
            if w in text:
                hits.append({"category": cat, "word": w})
    # 功效数字：如"三天""7天见效"
    for m in re.finditer(r"(\d+)\s*(天|日|周)\s*(见效|改善|变好)", text):
        hits.append({"category": "疗效时间承诺", "word": m.group(0)})
    return {"pass": not hits, "hits": hits, "hit_count": len(hits),
            "categories": sorted({h["category"] for h in hits})}


LIMIT = {"小红书": (300, 500), "抖音": (80, 150), "视频号": (120, 200)}


def rewrite_content(sample_id=None, text=None, platform="小红书", product="指压板"):
    """复写一条内容。有 key 走模型，无 key 走规则化降级版本。"""
    src = None
    if sample_id:
        samples = json.load(open(os.path.join(DATA, "content_samples.json"), encoding="utf-8"))
        src = next((s for s in samples if s["id"] == sample_id), None)
        if not src:
            return {"error": f"找不到样本 {sample_id}"}
    elif text:
        src = {"id": "custom", "platform": platform, "title": "", "body": text}
    else:
        return {"error": "需要 sample_id 或 text"}

    lo, hi = LIMIT.get(platform, (150, 400))
    before = compliance_check(src["body"])
    result = {"source_id": src["id"], "platform": platform,
              "before_compliance": before, "target_length": [lo, hi]}

    if llm.available():
        try:
            data = llm.chat_json([
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user", "content": f"平台：{platform}（{lo}-{hi}字）\n产品：{product}\n"
                                            f"原标题：{src.get('title', '')}\n原文：{src['body']}"}],
                temperature=0.7, max_tokens=1200)
            body = data.get("body", "")
            after = compliance_check(body)
            result.update({"title": data.get("title", ""), "body": body,
                           "changes": data.get("changes", []), "risk_flags": data.get("risk_flags", []),
                           "after_compliance": after, "mode": "llm",
                           "length": len(re.sub(r"\s", "", body))})
            return result
        except llm.LLMError as e:
            result["llm_error"] = str(e)

    # 离线降级：规则化改写，作用是把合规问题清掉，不追求文采
    body = src["body"]
    for words in BANNED.values():
        for w in words:
            body = body.replace(w, "")
    body = re.sub(r"(姐妹们谁懂啊！?|谁懂啊！?)", "", body)
    body = body.replace("链接放评论区了，冲！", "放在购物车里躺了几天，今天终于下单了。")
    body = body.strip("，。！ ") + "。"
    after = compliance_check(body)
    result.update({"title": src.get("title", "") or f"{platform}改写版",
                   "body": body, "mode": "offline_rule",
                   "changes": (["删除医疗功效与绝对化用语", "去掉泛开场", "硬引导改为软引导"]
                               if not before["pass"] else
                               ["原文无合规问题，问题在表达（缺场景/缺体感），离线模式不做文笔重写"]) +
                              ["注：离线模式只做合规清洗，接模型后可做完整改写"],
                   "after_compliance": after, "length": len(re.sub(r"\s", "", body))})
    return result


# ------------------------------------------------------------
# C. 数据复盘
# ------------------------------------------------------------

def review_campaign(group_by="content_type"):
    """按内容类型 / 达人层级 / 单个达人聚合，算 ROI、CTR、CVR、CPM。"""
    rows = _read_csv("campaign_performance.csv")
    agg = defaultdict(lambda: {"spend": 0.0, "gmv": 0.0, "imp": 0.0, "clk": 0.0,
                               "uv": 0.0, "orders": 0.0, "n": 0})
    for r in rows:
        key = r.get(group_by) or "unknown"
        a = agg[key]
        a["spend"] += _num(r["spend"]); a["gmv"] += _num(r["gmv"])
        a["imp"] += _num(r["impressions"]); a["clk"] += _num(r["clicks"])
        a["uv"] += _num(r["store_uv"]); a["orders"] += _num(r["orders"]); a["n"] += 1

    out = []
    for k, a in agg.items():
        roi = a["gmv"] / a["spend"] if a["spend"] else 0
        out.append({"group": k, "spend": round(a["spend"], 1), "gmv": round(a["gmv"], 1),
                    "roi": round(roi, 2),
                    "ctr": round(a["clk"] / a["imp"] * 100, 2) if a["imp"] else 0,
                    "cvr": round(a["orders"] / a["uv"] * 100, 2) if a["uv"] else 0,
                    "cpm": round(a["spend"] / a["imp"] * 1000, 2) if a["imp"] else 0,
                    "aov": round(a["gmv"] / a["orders"], 1) if a["orders"] else 0})
    out.sort(key=lambda x: -x["roi"])
    total_spend = sum(o["spend"] for o in out) or 1
    total_gmv = sum(o["gmv"] for o in out)
    return {"group_by": group_by, "rows": out,
            "overall": {"spend": round(total_spend, 1), "gmv": round(total_gmv, 1),
                        "roi": round(total_gmv / total_spend, 2)},
            "best": out[0]["group"] if out else None,
            "worst": out[-1]["group"] if out else None}


def diagnose_funnel(kol_id):
    """漏斗定位：把变化拆到曝光 / 点击率 / 转化率 / 客单价四环，指出掉在哪。"""
    rows = [r for r in _read_csv("campaign_performance.csv") if r["kol_id"] == kol_id]
    if not rows:
        return {"error": f"无 {kol_id} 的投放数据"}
    rows.sort(key=lambda r: r["dt"])
    half = max(len(rows) // 2, 1)
    early, late = rows[:half], rows[half:]

    def block(rs):
        imp = sum(_num(r["impressions"]) for r in rs) or 1
        clk = sum(_num(r["clicks"]) for r in rs)
        uv = sum(_num(r["store_uv"]) for r in rs) or 1
        od = sum(_num(r["orders"]) for r in rs)
        gmv = sum(_num(r["gmv"]) for r in rs)
        return {"曝光": imp, "点击率": clk / imp, "转化率": od / uv,
                "客单价": gmv / od if od else 0, "成交额": gmv}

    a, b = block(early), block(late)
    dev = {k: (b[k] - a[k]) / a[k] * 100 if a[k] else 0
           for k in ("曝光", "点击率", "转化率", "客单价")}
    main = max(dev, key=lambda k: abs(dev[k]))
    if abs(dev[main]) < 15:
        return {"kol_id": kol_id, "period": [rows[0]["dt"], rows[-1]["dt"]],
                "deviation_pct": {k: round(v, 1) for k, v in dev.items()},
                "main_driver": "无明显异常", "suggested_action": "波动在正常范围内，继续观察"}
    action = {
        "曝光": "查搜索排名与平台资源位，是否被限流或活动结束",
        "点击率": "主图/标题/首帧问题，核对是否有素材替换",
        "转化率": "落地页、价格、评价问题；先查详情页是否改版",
        "客单价": "是否在用低价 SKU 冲量，查货盘结构",
    }[main]
    return {"kol_id": kol_id, "period": [rows[0]["dt"], rows[-1]["dt"]],
            "early": {k: round(v, 3) for k, v in a.items()},
            "late": {k: round(v, 3) for k, v in b.items()},
            "deviation_pct": {k: round(v, 1) for k, v in dev.items()},
            "main_driver": main, "suggested_action": action}


# ------------------------------------------------------------
# D. 投放监测
# ------------------------------------------------------------

RULES = [
    {"name": "转化骤降", "metric": "cvr", "threshold": -0.30, "severity": "P0",
     "hint": "素材衰减或落地页异常，先停投再排查"},
    # 阈值 50%：短窗口内曝光放大一半以上、且转化没跟上，就值得看一眼
    {"name": "曝光异常飙升", "metric": "imp", "threshold": 0.50, "severity": "P1",
     "hint": "曝光涨但转化没涨，注意流量错配或刷量嫌疑"},
    {"name": "CPM 飙升", "metric": "cpm", "threshold": 0.40, "severity": "P1",
     "hint": "竞价环境变化或定向跑偏，考虑缩量"},
    {"name": "曝光腰斩", "metric": "imp", "threshold": -0.45, "severity": "P0",
     "hint": "疑似限流或内容被下架"},
]


def monitor_scan(recent=3, baseline=7):
    """滚动监测：近 N 天 vs 前 M 天，命中规则即告警。纯规则，可复现。"""
    rows = _read_csv("campaign_performance.csv")
    by_kol = defaultdict(list)
    for r in rows:
        by_kol[r["kol_id"]].append(r)

    alerts = []
    for kid, rs in by_kol.items():
        rs.sort(key=lambda r: r["dt"])
        if len(rs) < recent + baseline:
            continue
        pre, rec = rs[-(recent + baseline):-recent], rs[-recent:]

        def metrics(part):
            """用中位数而不是均值。

            异常期一旦被算进基线，均值会被自己稀释——曝光翻倍的那几天
            会把基线抬高，导致「涨幅不够」而漏报。中位数对少数异常日更稳。
            """
            imps = sorted(_num(r["impressions"]) for r in part)
            cvrs, cpms = [], []
            for r in part:
                uv = _num(r["store_uv"])
                if uv:
                    cvrs.append(_num(r["orders"]) / uv)
                imp = _num(r["impressions"])
                if imp:
                    cpms.append(_num(r["spend"]) / imp * 1000)
            med = lambda xs: xs[len(xs) // 2] if xs else 0.0
            return {"imp": med(imps), "cvr": med(sorted(cvrs)), "cpm": med(sorted(cpms))}

        a, b = metrics(pre), metrics(rec)
        for rule in RULES:
            m = rule["metric"]
            if not a[m]:
                continue
            delta = (b[m] - a[m]) / a[m]
            hit = delta <= rule["threshold"] if rule["threshold"] < 0 else delta >= rule["threshold"]
            if not hit:
                continue
            # 曝光飙升必须伴随转化不涨才算异常，否则是正常放量
            if rule["metric"] == "imp" and rule["threshold"] > 0:
                if (b["cvr"] - a["cvr"]) / a["cvr"] > -0.10:
                    continue
            alerts.append({"kol_id": kid, "rule": rule["name"], "severity": rule["severity"],
                           "metric": m, "baseline": round(a[m], 4), "recent": round(b[m], 4),
                           "delta_pct": round(delta * 100, 1), "hint": rule["hint"]})

    alerts.sort(key=lambda x: (x["severity"], -abs(x["delta_pct"])))
    return {"scanned_kols": len(by_kol), "window": {"recent_days": recent, "baseline_days": baseline},
            "alert_count": len(alerts),
            "by_severity": {s: sum(1 for a in alerts if a["severity"] == s) for s in ("P0", "P1")},
            "alerts": alerts}
