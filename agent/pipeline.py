#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
线索流水线：聊天记录 → 账号 → 画像 → 四维评分 → 飞书写入 → 货盘话术。

    ingest(texts)        抽账号（小红书号 / 抖音号 / 主页链接）
    enrich(accounts)     补画像（星火/飞瓜；未配置走 mock）
    score(profiles)      四维评分 + 分层
    breakdown(profile)   风格拆解（一句话说清他能怎么用）
    compose_outreach()   高匹配度才生成货盘 + 话术
    run_pipeline()       串起来，写飞书 + 推送汇总

**默认不自动私信达人**：生成待发队列，由人确认后推送。
理由见 docs/USAGE.md 的「合规边界」一节。
"""

import json
import os
import time

from . import core, integrations, llm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTBOX = os.path.join(ROOT, "outbox")

# 商品货盘（示例：真实使用时从商品库或手工配置读）
PRODUCT_PACK = [
    {"sku": "指压板·小号", "price": 39, "commission": 0.20, "point": "入门款，适合新手试水"},
    {"sku": "指压板·大号", "price": 59, "commission": 0.22, "point": "主力款，客单与转化最平衡"},
    {"sku": "指压板+收纳袋套装", "price": 89, "commission": 0.25, "point": "礼盒装，适合节日/送长辈"},
]


# ------------------------------------------------------------
# 1. 抽取
# ------------------------------------------------------------

def ingest(texts):
    accs, seen = [], set()
    for t in texts:
        for a in integrations.extract_accounts(t):
            k = (a["platform"], a["account_id"].lower())
            if k in seen:
                continue
            seen.add(k)
            a["source_text"] = t[:120]
            accs.append(a)
    return accs


# ------------------------------------------------------------
# 2. 补画像
# ------------------------------------------------------------

def enrich(accounts):
    client = integrations.ThirdPartyClient()
    out = []
    for a in accounts:
        p = client.profile(a["platform"], a["account_id"])
        p.setdefault("platform", a["platform"])
        p.setdefault("account_id", a["account_id"])
        p["mentioned_followers"] = a.get("mentioned_followers")
        p["context"] = a.get("context", "")
        out.append(p)
    return out


# ------------------------------------------------------------
# 3. 评分
# ------------------------------------------------------------

def _to_candidate(p, idx):
    return {
        "kol_id": p.get("account_id") or f"L{idx:03d}",
        "handle": p.get("handle") or f"{p.get('platform','')}号",
        "platform": p.get("platform"),
        "category": p.get("category"),
        "content_category": p.get("category"),
        "followers": int(p.get("followers") or 0),
        "price_band": p.get("price_band"),
        "audience_age": p.get("audience_age"),
        "audience_city": p.get("audience_city"),
        "engagement_rate": float(p.get("engagement_rate") or 0),
        "viral_rate": float(p.get("viral_rate") or 0),
        "comment_intent": float(p.get("comment_intent") or 0),
        "post_stability": float(p.get("post_stability") or 0.5),
        "exposure_30d": int(p.get("exposure_30d") or 0),
        "store_uv_30d": int(p.get("store_uv_30d") or 0),
        "orders_30d": int(p.get("orders_30d") or 0),
        "aov": float(p.get("aov") or 0),
        "quote": float(p.get("quote") or 0),
        "fulfill_rate": float(p.get("fulfill_rate") or 0.8),
        "repurchase_rate": float(p.get("repurchase_rate") or 0),
        "past_collab_footcare": p.get("past_collab_footcare") or "否",
    }


def score(profiles):
    cands = [_to_candidate(p, i) for i, p in enumerate(profiles, 1)]
    if not cands:
        return {"scored": 0, "rows": [], "tier_count": {}}

    # 用商品简报里的价格带做匹配基准（取不到就不设限）
    band = None
    try:
        stats = core.parse_product_sales()
        if "error" not in stats:
            band = core.build_brief(stats, "起量").get("价格带定位")
    except Exception:
        pass
    return core.score_candidates(cands, price_band=band)


# ------------------------------------------------------------
# 4. 风格拆解
# ------------------------------------------------------------

STYLE_HINT = {
    "实测型": "第一人称体感为主，适合讲「用了一周的真实感受」，不适合参数堆砌",
    "测评对比型": "擅长横向对比，适合打「同价位怎么选」，注意别引导贬损竞品",
    "生活vlog型": "场景自然，适合把产品放进日常动线，转化靠氛围不靠卖点",
    "知识科普型": "讲原理清晰，适合解释材质与结构，注意避开医疗表述",
    "种草型": "情绪驱动强，短期起量快，但复购与客单偏低，适合入门款",
}


def breakdown(p):
    if p.get("error"):
        return "画像获取失败，需人工核验后再定"
    style = p.get("style", "未知")
    hint = STYLE_HINT.get(style, "暂无风格标签")
    viral = float(p.get("viral_rate") or 0)
    stab = float(p.get("post_stability") or 0)
    content = ("近 30 天爆文率偏高，内容有爆发力" if viral > 0.2
               else "爆文率一般，靠稳定更新而非单条爆款")
    rhythm = "更新节奏稳" if stab < 0.35 else "更新波动大，排期要留缓冲"
    return f"{style}：{hint}；{content}；{rhythm}"


ACTION = {
    "S": "立即发货盘 + 优先排期",
    "A": "发货盘，进邀约队列",
    "B": "先寄样观察，暂不排期",
    "C": "暂不跟进，留档观察",
}


# ------------------------------------------------------------
# 5. 货盘与话术
# ------------------------------------------------------------

def compose_outreach(lead):
    """给单个高匹配达人配货盘 + 话术。有 key 用模型润色，否则用模板。"""
    pack = PRODUCT_PACK
    body = (
        f"你好，看到你在「{lead.get('category', '')}」方向的内容，"
        f"风格偏{lead.get('style', '实测')}，和我们这款足底按摩指压板挺搭。\n\n"
        f"给你一份货盘，三个价位都能挂：\n"
        + "\n".join(f"· {p['sku']}｜售价 {p['price']} 元｜佣金 {int(p['commission']*100)}%｜{p['point']}"
                    for p in pack)
        + f"\n\n如果合适，我按你的报价区间先寄一套样品，你试用后再定档期。"
    )
    tips = ["发送前确认对方近期是否仍在该垂类",
            "佣金比例按实际结算口径再核一次",
            "首次触达不要附购买链接"]

    if llm.available():
        try:
            data = llm.chat_json([
                {"role": "system", "content":
                    "你是达人商务。基于给定货盘写一条首次触达话术：先体现你了解对方内容，"
                    "再给三个 SKU 的价格与佣金，最后给一个低门槛下一步。不夸大功效，不用「亲/宝子」。"
                    "输出 JSON：{\"body\":\"...\",\"tips\":[\"...\"]}"},
                {"role": "user", "content":
                    f"达人：{lead.get('handle')}（{lead.get('platform')}，{lead.get('category')}，"
                    f"风格 {lead.get('style')}，粉丝 {lead.get('followers')}）\n"
                    + "\n".join(f"{p['sku']} 售价{p['price']} 佣金{int(p['commission']*100)}%" for p in pack)}],
                temperature=0.7, max_tokens=800)
            body = data.get("body") or body
            tips = data.get("tips") or tips
        except llm.LLMError:
            pass

    return {"pack": pack, "body": body, "tips": tips}


# ------------------------------------------------------------
# 6. 串起来
# ------------------------------------------------------------

def run_pipeline(texts, min_tier="A", write=True, push=False, use_llm_outreach=True):
    t0 = time.time()
    accs = ingest(texts)
    profiles = enrich(accs) if accs else []
    scored = score(profiles) if profiles else {"scored": 0, "rows": [], "tier_count": {}}

    by_id = {p.get("account_id"): p for p in profiles}
    rows, leads, queue = [], [], []

    for r in scored.get("rows", []):
        p = by_id.get(r["kol_id"], {})
        tier = r.get("tier", "C")
        action = ACTION.get(tier, ACTION["C"])
        lead = {
            "platform": r.get("platform"), "account_id": r["kol_id"],
            "handle": r.get("handle"), "category": p.get("category"),
            "style": p.get("style"), "followers": r.get("followers"),
            "quote": r.get("quote"), "score": r.get("total"), "tier": tier,
            "summary": integrations.profile_style_summary(p),
            "breakdown": breakdown(p),
            "action": action,
        }

        high = tier in ("S", "A") and (min_tier == "A" or tier == "S")
        lead["outreach"] = None
        if high:
            lead["outreach"] = compose_outreach(lead) if use_llm_outreach else compose_outreach(
                {**lead, "_offline": True})
            queue.append({"lead": lead, "outreach": lead["outreach"]})

        leads.append(lead)
        rows.append({
            "抓取时间": time.strftime("%Y-%m-%d %H:%M"),
            "平台": lead["platform"], "账号ID": lead["account_id"],
            "达人昵称": lead["handle"], "内容方向": lead["category"],
            "风格": lead["style"], "粉丝数": lead["followers"],
            "近30天曝光": p.get("exposure_30d"), "客单价": p.get("aov"),
            "报价": lead["quote"], "匹配分": lead["score"], "分层": tier,
            "风格拆解": lead["breakdown"], "建议动作": lead["action"],
            "话术状态": "待确认" if high else "不生成",
        })

    writer = integrations.FeishuWriter()
    result = {"written": 0, "mode": "skipped"}
    if write and rows:
        result = writer.write(rows)

    pushed = None
    if push:
        head = (f"【达人线索】新增 {len(rows)} 条，高匹配 {len(queue)} 条\n"
                + "\n".join(f"{r['平台']} {r['账号ID']}｜{r['分层']}｜{r['匹配分']}分｜{r['建议动作']}"
                            for r in rows[:8]))
        pushed = integrations.wecom_send(head)

    return {
        "accounts_found": len(accs),
        "profiles": len(profiles),
        "scored": scored.get("scored", 0),
        "tier_count": scored.get("tier_count", {}),
        "leads": leads,
        "rows": rows,
        "outreach_queue": queue,
        "write_result": result,
        "push_result": pushed,
        "elapsed_ms": int((time.time() - t0) * 1000),
        "provider": integrations.ThirdPartyClient().provider,
    }


def save_queue(queue):
    """把待发队列落盘，供人工确认后逐条发送。"""
    os.makedirs(OUTBOX, exist_ok=True)
    p = os.path.join(OUTBOX, f"outreach_queue_{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
    return p
