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

from . import datasource, llm
from .core import parse_product_sales

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")


# ------------------------------------------------------------
# 通用读取
# ------------------------------------------------------------

def _read_csv(name):
    """统一走数据源抽象：csv / sql / http 都能用同一个名字取到数据。"""
    mapping = {"candidates.csv": "candidates",
               "campaign_performance.csv": "campaign",
               "content_samples.json": "content_samples"}
    ds = mapping.get(name)
    if ds:
        return datasource.load(ds)
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
5. 正文长度必须落在平台区间内，低于下限视为不合格：小红书 300-500 字，抖音口播 80-150 字，视频号 120-200 字
6. 不得出现违禁词原词，包括否定句和引用句（例如「不是疏通经络」也不行）；序数「第一次」改写为「头一次」或「刚开始」，避免命中绝对化词表
7. 结尾只用「按需看看 / 有需要可以了解」这类软引导，不要出现「评论区放链接」「点击购买」「冲」

输出 JSON：{"title": "...", "body": "...", "changes": ["改了什么，为什么"], "risk_flags": ["仍需人工确认的点"]}"""


REPAIR_SYSTEM = """你是内容合规编辑。下面这段文案仍命中平台违禁词。
请在不改变原意、不降低可读性的前提下重写，确保命中词的原词一个都不出现——
否定句、引用句也不允许（「不是疏通经络」也会命中）；「第一次」改成「头一次」或「刚开始」。
不要新增任何功效、疗效、绝对化表述，也不要新增购买指令。
只输出 JSON：{"title": "...", "body": "...", "changes": ["改了什么"]}"""


LENGTH_SYSTEM = """你是内容编辑。下面文案的长度不符合平台要求。
请在保持事实、原意与平台调性的前提下调整正文长度到目标区间（中文按不含空格字符数计）。
硬性要求：不新增疗效、医疗功效、绝对化用语或购买指令；不得出现违禁词原词（否定句也不行）。
只输出 JSON：{"title": "...", "body": "...", "changes": ["长度怎么调的"]}"""


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
        samples = datasource.load("content_samples")
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

    # RAG：检索品牌语气 / 合规规则 / 平台要求，注入改写提示
    rag_hits, rag_ctx = [], ""
    try:
        from . import rag as _rag
        rag_hits, rag_ctx = _rag.search_context(
            f"{platform} {product} 内容 合规 字数 品牌语气", top_k=3)
        result["rag_hits"] = [{"doc": h["doc"], "title": h["title"], "score": h["score"]}
                              for h in rag_hits]
    except Exception:
        pass

    if llm.available():
        try:
            rag_block = (f"参考知识库（BM25 检索命中，按需引用，不要照抄）：\n{rag_ctx}\n\n"
                         if rag_ctx else "")
            data = llm.chat_json([
                {"role": "system", "content": REWRITE_SYSTEM},
                {"role": "user", "content": rag_block + f"平台：{platform}（{lo}-{hi}字）\n产品：{product}\n"
                                            f"原标题：{src.get('title', '')}\n原文：{src['body']}"}],
                temperature=0.7, max_tokens=1200)
            body = data.get("body", "")
            title = data.get("title", "")
            changes = list(data.get("changes", []) or [])
            after = compliance_check(body)
            repaired = False

            # 复写后仍命中 → 带着命中词让模型改一次（最多一次，避免死循环）
            if not after["pass"]:
                hit_words = sorted({h["word"] for h in after["hits"]})
                try:
                    fixed = llm.chat_json([
                        {"role": "system", "content": REPAIR_SYSTEM},
                        {"role": "user", "content":
                            f"平台：{platform}\n命中词：{'、'.join(hit_words)}\n"
                            f"标题：{title}\n正文：{body}"}],
                        temperature=0.3, max_tokens=1200)
                    body2 = fixed.get("body") or body
                    after2 = compliance_check(body2)
                    if after2["hit_count"] < after["hit_count"]:
                        body, after = body2, after2
                        title = fixed.get("title") or title
                        changes += [f"合规修复：{c}" for c in (fixed.get("changes") or [])]
                        repaired = True
                except llm.LLMError:
                    pass

            length = len(re.sub(r"\s", "", body))
            length_fixed = False
            # 长度不在目标区间（低于下限或明显超上限）→ 再调一次
            if length < lo or length > hi * 1.2:
                try:
                    fixed = llm.chat_json([
                        {"role": "system", "content": LENGTH_SYSTEM},
                        {"role": "user", "content":
                            f"平台：{platform}\n目标长度：{lo}-{hi} 字（当前 {length} 字）\n"
                            f"标题：{title}\n正文：{body}"}],
                        temperature=0.5, max_tokens=1400)
                    body2 = fixed.get("body") or body
                    after2 = compliance_check(body2)
                    n2 = len(re.sub(r"\s", "", body2))
                    if after2["pass"] and lo * 0.95 <= n2 <= hi * 1.2:
                        body, after, length = body2, after2, n2
                        title = fixed.get("title") or title
                        changes += [f"长度调整：{c}" for c in (fixed.get("changes") or [])]
                        length_fixed = True
                except llm.LLMError:
                    pass

            result.update({"title": title, "body": body, "changes": changes,
                           "risk_flags": data.get("risk_flags", []),
                           "after_compliance": after, "mode": "llm", "repaired": repaired,
                           "length_fixed": length_fixed, "length": length})
            return result
        except llm.LLMError as e:
            result["llm_error"] = str(e)

    # 离线降级：规则化改写。按整句丢弃命中违禁词的句子，而不是做词级替换——
    # 词级替换会把「而且还…，必备！了。冲。」这种残句留在正文里。
    raw = re.sub(r"^(姐妹们谁懂啊[！!，,]*|谁懂啊[！!，,]*|家人们[！!，,]*|宝子们[！!，,]*)",
                 "", src["body"]).strip()
    parts = re.split(r"(?<=[。！!？?；;])\s*", raw)
    banned_words = [w for words in BANNED.values() for w in words]
    kept = [p.strip() for p in parts if p.strip() and not any(w in p for w in banned_words)]
    body = "".join(kept).strip("，。！!；; ")
    tail = {
        "小红书": "放在书桌下面，想起来就踩一会儿，比一直瘫着强。",
        "抖音": "放桌下，想起来踩两下就行。",
        "视频号": "放在家里随手能踩到的地方，比刻意抽时间更容易坚持。",
    }.get(platform, "放在随手能用到的地方，先试一周。")
    if body and not body.endswith(("。", "！", "!", "？", "?")):
        body += "。"
    body = (body + tail) if body else tail
    body = body.replace("。。", "。")
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
        # 这是「这个达人没有投放记录」的业务结果，不是工具故障。
        # 返回 error 会命中 BLOCK 护栏，让整个任务因为一个辅助诊断而终止。
        return {"kol_id": kol_id, "found": False,
                "message": f"没有 {kol_id} 的投放记录，无法做漏斗诊断",
                "suggestion": "换一个有投放记录的达人，或先看 monitor_scan 的告警名单"}
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


# ------------------------------------------------------------
# E. 可直接发出去的产出：邀约话术 / 日报
# ------------------------------------------------------------

OUTREACH_SYSTEM = """你是达人商务，写一条首次邀约私信。

要求：
1. 前两句必须让对方知道「你了解他的内容」，提到具体内容方向或受众，不要群发感
2. 说清三件事：合作形式、预算区间、需要他做什么
3. 不夸大产品功效，不承诺效果，不写医疗相关表述
4. 结尾给一个低门槛的下一步（发个样品 / 约 15 分钟沟通），不要逼单
5. 150 字以内，口语，不用「亲」「宝子」这类称呼

输出 JSON：{"subject": "一句话主题", "body": "正文", "tips": ["发送前要确认的点"]}"""


def draft_outreach_message(kol_ids, channel="私信"):
    """为指定达人生成邀约话术。有 key 走模型，无 key 用模板。"""
    cands = {c["kol_id"]: c for c in _read_csv("candidates.csv")}
    out = []
    for kid in kol_ids[:5]:
        c = cands.get(kid)
        if not c:
            out.append({"kol_id": kid, "error": "候选人池中无此 id"})
            continue
        q = float(c["quote"])
        low, high = round(q * 0.75), round(q * 0.95)

        if llm.available():
            try:
                data = llm.chat_json([
                    {"role": "system", "content": OUTREACH_SYSTEM},
                    {"role": "user", "content":
                        f"达人：{c['handle']}（{c['platform']}，{c['category']}，"
                        f"粉丝 {c['followers']}，受众 {c['audience_age']} 岁 / {c['audience_city']}）\n"
                        f"产品：足底按摩指压板（居家健身器材，非医疗器械）\n"
                        f"预算区间：{low}–{high} 元\n渠道：{channel}"}],
                    temperature=0.7, max_tokens=700)
                out.append({"kol_id": kid, "handle": c["handle"], "channel": channel,
                            "subject": data.get("subject", ""), "body": data.get("body", ""),
                            "tips": data.get("tips", []), "mode": "llm"})
                continue
            except llm.LLMError:
                pass

        body = (
            f"你好，我是做家清与居家健身类目的商务。看到你在「{c['category']}」方向的内容，"
            f"尤其是面向 {c['audience_age']} 岁、{c['audience_city']}人群那几条，节奏和真实感我们很认可。\n\n"
            f"这次想合作一款足底按摩指压板：{channel} 单条内容，预算 {low}–{high} 元，"
            f"需要你按我们给的卖点方向出稿，脚本先过一版再拍。\n\n"
            f"如果方向合适，我先寄一套样品给你试试，用着顺手再谈档期。方便的话回我一句就行。"
        )
        out.append({"kol_id": kid, "handle": c["handle"], "channel": channel,
                    "subject": f"{c['handle']} × 指压板合作邀约",
                    "body": body,
                    "tips": ["发送前确认对方近期内容方向是否仍是该垂类",
                             "报价区间按 75–95 折给，留出谈判空间",
                             "不要在首次私信里附产品链接，容易被判营销"],
                    "mode": "offline_template"})
    return {"messages": out, "count": len(out)}


def compose_daily_report(budget=8000.0, top_n=5):
    """生成给主管看的日报：一屏说清「昨天怎么样、今天要做什么」。"""
    mon = monitor_scan()
    rev = review_campaign("content_type")
    stats = parse_product_sales()

    p0 = [a for a in mon.get("alerts", []) if a["severity"] == "P0"]
    p1 = [a for a in mon.get("alerts", []) if a["severity"] == "P1"]

    lines = ["# 达人投放日报", ""]
    lines.append(f"数据源：{stats.get('数据源', 'n/a')}　｜　监控窗口：近 {mon['window']['recent_days']} 天 vs 前 {mon['window']['baseline_days']} 天")
    lines.append("")

    lines.append("## 一、整体")
    o = rev["overall"]
    lines.append(f"- 花费 {o['spend']:,.0f} 元，成交 {o['gmv']:,.0f} 元，整体 ROI **{o['roi']}**")
    lines.append(f"- 内容类型表现：最好 **{rev['best']}**，最差 **{rev['worst']}**")
    lines.append(f"- 商品侧客单价 {stats.get('估算客单价')} 元（置信度{stats.get('客单价_置信度')}）")
    lines.append("")

    lines.append(f"## 二、要动的（{len(p0) + len(p1)} 条）")
    if not p0 and not p1:
        lines.append("- 本期未命中告警阈值。注意：无告警不等于无风险，可能是阈值过宽。")
    for a in (p0 + p1):
        lines.append(f"- **[{a['severity']}] {a['kol_id']} {a['rule']}（{a['delta_pct']}%）** — {a['hint']}")
    lines.append("")

    lines.append("## 三、建议动作")
    acts = []
    for a in p0:
        acts.append(f"{a['kol_id']} 先停投，排查{a['rule']}原因")
    if rev["worst"]:
        acts.append(f"把预算从「{rev['worst']}」向「{rev['best']}」倾斜")
    if len(acts) < 3:
        acts.append("对 S/A 层达人补发合作 brief，锁定下周档期")
    for i, t in enumerate(acts[:4], 1):
        lines.append(f"{i}. {t}")
    lines.append("")

    lines.append("## 四、需要人工确认")
    lines.append("- 监测阈值是经验值，未做本品类校准")
    lines.append("- 内容类产出需人工终审后发布")
    lines.append(f"- 预算口径按 {budget:,.0f} 元计算，实际以财务为准")

    return {"markdown": "\n".join(lines), "p0": len(p0), "p1": len(p1),
            "roi": o["roi"], "top_n": top_n}
