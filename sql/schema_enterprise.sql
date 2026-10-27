-- ============================================================
-- 企业库对接参考表结构（以抖音电商罗盘导出为准，字段可按实情替换）
-- 用途：示例/演示。真实接入时保留列名对齐 sql/mapping.json 即可。
-- ============================================================

-- 商品销售分布（日粒度，字段口径同罗盘「商品详情-销售分布」）
CREATE TABLE IF NOT EXISTS product_sales_daily (
    "日期"          TEXT PRIMARY KEY,
    "销量"          TEXT,      -- 平台导出常为区间：'5000-1w'
    "销售额"        TEXT,      -- '10w-25w'
    "商品卡销量"    TEXT,
    "商品卡销售额"  TEXT,
    "直播销量"      TEXT,
    "直播销售额"    TEXT,
    "视频销量"      TEXT,
    "视频销售额"    TEXT,
    "浏览量"        INTEGER,   -- 数值，不区间化
    "订单量"        TEXT,
    "转化率"        TEXT,      -- '5%-10%'
    "带货视频"      INTEGER,
    "带货直播"      INTEGER,
    "带货达人"      INTEGER,
    "视频带货达人"  INTEGER,
    "直播带货达人"  INTEGER
);

-- 达人主数据
CREATE TABLE IF NOT EXISTS dim_kol (
    kol_id                 TEXT PRIMARY KEY,
    handle                 TEXT,
    platform               TEXT,
    category               TEXT,
    content_category       TEXT,
    followers              INTEGER,
    price_band             TEXT,
    audience_age           TEXT,
    audience_city          TEXT,
    engagement_rate        REAL,
    viral_rate             REAL,
    comment_intent         REAL,
    post_stability         REAL,
    exposure_30d           INTEGER,
    store_uv_30d           INTEGER,
    orders_30d             INTEGER,
    aov                    REAL,
    quote                  REAL,
    fulfill_rate           REAL,
    repurchase_rate        REAL,
    past_collab_footcare   TEXT,
    status                 TEXT DEFAULT 'active'   -- active / blocked / archived
);

-- 达人投放日明细
CREATE TABLE IF NOT EXISTS fact_kol_daily (
    dt           TEXT NOT NULL,
    kol_id       TEXT NOT NULL,
    content_type TEXT,
    tier         TEXT,
    impressions  INTEGER,
    clicks       INTEGER,
    store_uv     INTEGER,
    orders       INTEGER,
    gmv          REAL,
    spend        REAL,
    aov          REAL,
    PRIMARY KEY (dt, kol_id),
    FOREIGN KEY (kol_id) REFERENCES dim_kol(kol_id)
);

-- 待复写内容样本
CREATE TABLE IF NOT EXISTS dim_content_sample (
    id       TEXT PRIMARY KEY,
    platform TEXT,
    title    TEXT,
    body     TEXT,
    problem  TEXT
);

CREATE INDEX IF NOT EXISTS idx_kol_daily_dt  ON fact_kol_daily(dt);
CREATE INDEX IF NOT EXISTS idx_kol_daily_kol ON fact_kol_daily(kol_id);
