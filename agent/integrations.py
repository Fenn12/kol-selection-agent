#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
外部系统接入层：企业微信 / 星火·飞瓜 / 飞书多维表格。

三个适配器都是「有凭证走真实接口，没凭证走本地兜底」的形式，
保证任何环境都能跑通链路，而不是没配就报错。

────────────────────────────────────────────────────────
企业微信的现实限制（必须知道）
────────────────────────────────────────────────────────
1. 群机器人 webhook 只能**往外发**，不能读聊天记录。
2. 读聊天记录只有两条路：
   a) 自建应用 + 消息回调（需要公网可达的回调地址）
   b) 会话内容存档（需要企业开通、通过服务商 SDK、拿到私钥）
   两条路都要企业管理员配合，不是技术侧能单方面搞定的。
3. 因此本仓库的做法是：
   - 提供 /api/wecom/ingest 接收**回调推送**或**导出的会话 JSON**
   - 提供本地粘贴/文件导入，先跑通解析与评分链路
   - 群机器人只用于「把待办推给运营群」，不做私信陌生达人

────────────────────────────────────────────────────────
星火 / 飞瓜
────────────────────────────────────────────────────────
两家都没有公开免费 API。飞瓜有开放平台（需商务开通），星火（新红）
同理。所以这里定义了 ThirdPartyClient 接口 + 一个 mock 实现，
真实接入时把 base_url / token 填进环境变量即可，业务代码不改。
"""

import hashlib
import json
import os
import random
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTBOX = os.path.join(ROOT, "outbox")


# ============================================================
# 1. 企业微信：消息解析 + 群机器人推送
# ============================================================

# 小红书：xhs 号 / 主页链接 / 「小红书号：xxx」
# 抖音：抖音号 / v.douyin.com 短链 / 主页链接
PATTERNS = [
    ("小红书", re.compile(r"xiaohongshu\.com/user/profile/([A-Za-z0-9]+)")),
    ("小红书", re.compile(r"xhslink\.com/([A-Za-z0-9]+)")),
    ("小红书", re.compile(r"小红书号[：:\s]*([A-Za-z0-9_\-]{4,20})")),
    ("抖音", re.compile(r"v\.douyin\.com/([A-Za-z0-9]+)")),
    ("抖音", re.compile(r"douyin\.com/user/([A-Za-z0-9_\-]+)")),
    ("抖音", re.compile(r"抖音号[：:\s]*([A-Za-z0-9_.\-]{4,24})")),
]

# 粉丝量写法：12.3w粉丝 / 8000 粉 / 粉丝 4.5万
# 前面加 (?<![\w.]) 是为了避免把「抖音号：jiuzuo2024 粉丝」里的 2024 当成粉丝数
FOLLOWER_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([wW万]?)\s*(?:粉丝|粉)")
FOLLOWER_RE2 = re.compile(r"粉丝[：:\s]*(\d+(?:\.\d+)?)\s*([wW万]?)")


def extract_accounts(text):
    """从一段聊天文本里抽出平台 + 账号 ID + 上下文。

    不做"猜"：抽不到就返回空列表，让上游决定要不要人工补录。
    """
    if not text:
        return []
    found, seen = [], set()

    for platform, pat in PATTERNS:
        for m in pat.finditer(text):
            acc = m.group(1).strip()
            key = (platform, acc.lower())
            if key in seen:
                continue
            seen.add(key)

            # 取账号前后 40 字作为上下文，便于人工核对
            s, e = max(m.start() - 40, 0), min(m.end() + 40, len(text))
            ctx = text[s:e].replace("\n", " ").strip()

            followers = None
            fm = FOLLOWER_RE.search(ctx) or FOLLOWER_RE2.search(ctx)
            if fm:
                n = float(fm.group(1))
                if fm.group(2) in ("w", "W", "万"):
                    n *= 10000
                # 数值太小说明不是粉丝数（多半是账号 ID 里的数字）
                if n >= 100:
                    followers = int(n)

            found.append({"platform": platform, "account_id": acc,
                          "raw": m.group(0), "context": ctx,
                          "mentioned_followers": followers})
    return found


def parse_wecom_payload(payload):
    """兼容三种输入：回调 JSON / 会话存档导出 / 手工粘贴。"""
    texts = []

    if isinstance(payload, str):
        texts.append(payload)
    elif isinstance(payload, dict):
        # 自建应用消息回调
        if payload.get("text", {}).get("content"):
            texts.append(payload["text"]["content"])
        if payload.get("content"):
            texts.append(payload["content"])
        # 会话存档：messages 数组
        for m in payload.get("messages", []) or []:
            if isinstance(m, str):
                texts.append(m)
            elif isinstance(m, dict):
                texts.append(m.get("text") or m.get("content") or "")
    elif isinstance(payload, list):
        for m in payload:
            texts.extend(parse_wecom_payload(m))

    return [t for t in texts if t]


def wecom_configured():
    return bool(os.getenv("WECOM_BOT_WEBHOOK"))


def wecom_send(text, webhook=None, dry_run=None):
    """推送到企微群机器人。未配置则落盘，便于验证链路。"""
    webhook = webhook or os.getenv("WECOM_BOT_WEBHOOK")
    if dry_run is None:
        dry_run = not webhook

    if dry_run:
        os.makedirs(OUTBOX, exist_ok=True)
        p = os.path.join(OUTBOX, "wecom_outbox.jsonl")
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
        return {"sent": False, "mode": "dry_run", "path": p}

    body = json.dumps({"msgtype": "text", "text": {"content": text}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=body,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode("utf-8") or "{}")
        ok = resp.get("errcode", -1) == 0
        return {"sent": ok, "mode": "webhook", "resp": resp}
    except Exception as e:
        return {"sent": False, "mode": "webhook", "error": f"{type(e).__name__}: {e}"}


# ============================================================
# 2. 星火 / 飞瓜：第三方数据
# ============================================================

class ThirdPartyClient:
    """第三方达人数据接口。真实实现按 base_url + token 走；mock 用确定性伪数据。"""

    def __init__(self):
        self.base = (os.getenv("KOL_TP_BASE") or "").rstrip("/")
        self.token = os.getenv("KOL_TP_TOKEN")
        self.provider = (os.getenv("KOL_TP_PROVIDER") or "mock").lower()

    def available(self):
        return bool(self.base and self.token)

    def profile(self, platform, account_id):
        if self.available():
            return self._remote(platform, account_id)
        return self._mock(platform, account_id)

    def _remote(self, platform, account_id):
        url = f"{self.base}/creator/profile?platform={platform}&id={account_id}"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}", "account_id": account_id}

    def _mock(self, platform, account_id):
        """用 account_id 的哈希做种子，保证同一账号每次结果一致。"""
        seed = int(hashlib.md5(f"{platform}:{account_id}".encode()).hexdigest()[:8], 16)
        rnd = random.Random(seed)

        cats = ["运动健身", "健康养生", "家居生活", "好物测评", "生活方式"]
        styles = ["实测型", "测评对比型", "生活vlog型", "知识科普型", "种草型"]
        bands = ["低客单", "中客单", "中高客单", "高客单"]

        followers = int(10 ** rnd.uniform(3.3, 5.4))
        exposure = int(followers * rnd.uniform(0.6, 2.6))
        store_uv = max(int(exposure * rnd.uniform(0.015, 0.075)), 1)

        return {
            "account_id": account_id,
            "platform": platform,
            "provider": "mock",
            "handle": f"{platform}号_{account_id[-4:]}",
            "followers": followers,
            "category": rnd.choice(cats),
            "style": rnd.choice(styles),
            "price_band": rnd.choice(bands),
            "audience_age": rnd.choice(["18-24", "25-30", "30-40"]),
            "audience_city": rnd.choice(["一线", "新一线", "二线"]),
            "engagement_rate": round(rnd.uniform(0.012, 0.085), 4),
            "viral_rate": round(rnd.uniform(0.01, 0.38), 4),
            "comment_intent": round(rnd.uniform(0.05, 0.5), 4),
            "post_stability": round(rnd.uniform(0.1, 0.7), 4),
            "exposure_30d": exposure,
            "store_uv_30d": store_uv,
            "orders_30d": int(store_uv * rnd.uniform(0.008, 0.055)),
            "aov": round(rnd.uniform(60, 260), 0),
            "quote": int(followers * rnd.uniform(0.012, 0.045) / 10) * 10,
            "fulfill_rate": round(rnd.uniform(0.6, 1.0), 2),
            "repurchase_rate": round(rnd.uniform(0.0, 0.25), 3),
            "past_collab_footcare": rnd.choices(["是", "否"], weights=[35, 65])[0],
            "note": "mock 数据：未配置 KOL_TP_BASE / KOL_TP_TOKEN，按账号 ID 稳定生成",
        }


def profile_style_summary(p):
    """把原始画像压成一句人话，写进飞书/推送时用。"""
    if p.get("error"):
        return "画像获取失败，需人工核验"
    return (f"{p.get('style', '未知')}｜{p.get('category', '')}｜"
            f"粉丝 {p.get('followers', 0):,}｜受众 {p.get('audience_age', '')}/{p.get('audience_city', '')}｜"
            f"近30天曝光 {p.get('exposure_30d', 0):,}")


# ============================================================
# 3. 飞书多维表格
# ============================================================

class FeishuWriter:
    """写入飞书多维表格。

    配置：FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_BITABLE_APP_TOKEN / FEISHU_BITABLE_TABLE_ID
    未配置时写本地 CSV（outbox/leads_*.csv），字段与表格一致，可直接导入。
    """

    COLUMNS = ["抓取时间", "平台", "账号ID", "达人昵称", "内容方向", "风格",
               "粉丝数", "近30天曝光", "客单价", "报价", "匹配分", "分层",
               "风格拆解", "建议动作", "话术状态"]

    def __init__(self):
        self.app_id = os.getenv("FEISHU_APP_ID")
        self.secret = os.getenv("FEISHU_APP_SECRET")
        self.app_token = os.getenv("FEISHU_BITABLE_APP_TOKEN")
        self.table_id = os.getenv("FEISHU_BITABLE_TABLE_ID")

    def available(self):
        return all([self.app_id, self.secret, self.app_token, self.table_id])

    def _token(self):
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        body = json.dumps({"app_id": self.app_id, "app_secret": self.secret}).encode()
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            d = json.loads(r.read().decode())
        return d.get("tenant_access_token")

    def write(self, rows):
        if not rows:
            return {"written": 0, "mode": "empty"}

        if self.available():
            return self._write_bitable(rows)
        return self._write_csv(rows)

    def _write_bitable(self, rows):
        try:
            tk = self._token()
            url = (f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}"
                   f"/tables/{self.table_id}/records/batch_create")
            payload = {"records": [{"fields": r} for r in rows]}
            req = urllib.request.Request(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                         headers={"Content-Type": "application/json",
                                                  "Authorization": f"Bearer {tk}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                d = json.loads(r.read().decode("utf-8"))
            ok = d.get("code") == 0
            return {"written": len(rows) if ok else 0, "mode": "bitable",
                    "ok": ok, "resp_code": d.get("code"), "msg": d.get("msg")}
        except Exception as e:
            fallback = self._write_csv(rows)
            fallback["error"] = f"{type(e).__name__}: {e}"
            return fallback

    def _write_csv(self, rows):
        import csv
        import time
        os.makedirs(OUTBOX, exist_ok=True)
        p = os.path.join(OUTBOX, f"leads_{time.strftime('%Y%m%d-%H%M%S')}.csv")
        with open(p, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=self.COLUMNS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        return {"written": len(rows), "mode": "csv", "path": p,
                "note": "未配置飞书凭证，已写本地 CSV，可直接导入多维表格"}
