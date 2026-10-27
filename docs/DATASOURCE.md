# 接入企业内部数据源

三种方式，按你们现有条件选一种。**业务代码一行都不用改。**

```
KOL_DATASOURCE=csv    默认，读 data/*.csv
KOL_DATASOURCE=sql    读数据库，SQL 写在 sql/mapping.json
KOL_DATASOURCE=http   调内网 API
```

---

## 方式一：改 SQL（最省事）

适合：数据已经在数仓或业务库，能直连只读账号。

**1. 准备四个查询**，写进 `sql/mapping.json` 的 `queries`：

```json
{
  "queries": {
    "product_sales": "SELECT * FROM dws.daily_product_sales WHERE dt >= :start",
    "candidates":    "SELECT * FROM dim.kol WHERE status='active'",
    "campaign":      "SELECT * FROM dws.kol_daily",
    "content_samples": "SELECT * FROM dim.content_sample"
  }
}
```

**2. 字段名对不上就加映射**（左边你的列名，右边本仓库标准名）：

```json
{
  "columns": {
    "candidates": {
      "kol_id": "KOL_ID",
      "handle": "NICK_NAME",
      "followers": "FANS_CNT",
      "quote": "QUOTED_PRICE",
      "past_collab_footcare": "HAS_FOOT_CARE_CATEGORY"
    }
  }
}
```

未列出的字段原样保留——**只映射你关心的，不用一次写全**。

**3. 配连接串**：

```bash
# MySQL
export KOL_DATASOURCE=sql
export KOL_DB_URL="mysql://reader:pass@10.0.0.12:3306/marketing"

# PostgreSQL
export KOL_DB_URL="postgresql://reader:pass@10.0.0.12:5432/marketing"

# 先本地验证（不需要任何驱动）
python scripts/build_sqlite_demo.py
export KOL_DATASOURCE=sql
export KOL_DB_URL="sqlite:///data/demo.db"
python run_agent.py --goal "起量"
```

MySQL 需 `pip install pymysql`，PostgreSQL 需 `pip install psycopg2-binary`。

---

## 方式二：自己实现连接（驱动不匹配时用）

适合：Oracle、达梦、ClickHouse，或需要走内网代理 / 连接池 / 脱敏中间件。

写一个模块，暴露 `connect()` 返回任意 DB-API 连接对象：

```python
# my_pkg/kol_db.py
import our_internal_db

def connect():
    return our_internal_db.connect(  # 返回 DB-API Connection 即可
        dsn="internal://marketing", pool_size=4, read_only=True
    )
```

然后：

```bash
export KOL_DATASOURCE=sql
export KOL_DB_MODULE=my_pkg.kol_db
```

查询语句仍从 `sql/mapping.json` 读，所以**换库不用改 SQL 写法**，只要保证返回列名能对上。

---

## 方式三：内网 API

适合：数据库不能直连，但内部有数据服务。

```bash
export KOL_DATASOURCE=http
export KOL_API_BASE=http://data-gateway.internal/api/kol
export KOL_API_TOKEN=xxxx
```

仓库会依次请求：

```
GET /product_sales
GET /candidates
GET /campaign
GET /content_samples
```

要求返回 JSON 数组，或 `{"data": [...]}`。字段名同样可用 `sql/mapping.json` 的 `columns` 做映射。

---

## 数据契约（必须满足，否则分析会失真）

| 数据集 | 关键要求 |
|---|---|
| `product_sales` | **必须有一行 `日期='总计'`**；没有则按日累加（暂未实现，会报错） |
| `product_sales` | `销量/销售额/转化率` 等可以是区间字符串（`5000-1w`、`5%-10%`）或数值；`浏览量` 建议给数值 |
| `candidates` | `kol_id` 唯一；`quote` 是单条内容报价；比率类字段给小数（`0.045` 而非 `4.5`） |
| `campaign` | 至少覆盖最近 10 天，否则监测会跳过该达人（需要 recent 3 + baseline 7） |
| `content_samples` | `body` 为待改写的原文全文 |

**口径提醒**：`销售额` 请明确是含税/不含税、优惠前/后、扣不扣退货。本仓库默认「优惠后、未扣退货」，与抖音电商罗盘导出一致。口径不一致会让 ROI 直接算错。

---

## 常见问题

**Q：字段名是中文可以吗？**
可以，SQLite 里用双引号包住即可；其他库建议加别名。

**Q：能不能只接一部分数据？**
可以。比如只接 `campaign`（拿真实投放数据做复盘），其余仍用样例：
目前是整源切换，若要混合，在 `agent/datasource.py` 里给对应 dataset 加 fallback 分支即可（5 行代码）。

**Q：数据量很大怎么办？**
在 SQL 里加时间窗口（如 `WHERE dt >= DATE_SUB(NOW(), INTERVAL 90 DAY)`）。当前分析只需要近 28 天与去年同期，全表拉取没有意义。

**Q：会不会把生产库拖慢？**
所有查询都是单表 `SELECT`，无 JOIN、无聚合下推。建议用只读从库，并在 `KOL_DB_URL` 里配置只读账号。

**Q：敏感字段怎么处理？**
达人手机号、真实姓名等不需要进本系统。`mapping.json` 只映射分析需要的字段，其余不查即可——**最小化取数比事后脱敏可靠**。
