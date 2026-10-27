# KOL Operations Agent

> **English abstract** — A tool-using agent covering the full creator-marketing loop: creator selection → outreach brief → content rewriting → performance review → live monitoring. Fourteen tools, two planners (LLM function-calling / offline rule baseline), and a guard layer that makes the agent **refuse** instead of fabricate when data is missing, budget is short, or candidates are empty. The LLM planner runs **plan → act → observe → repair → self-check**: it writes its own execution plan, calls tools on its own, and audits every number in its answer against a tool result before finalizing. Eleven behavioural evals.

一个覆盖「达人筛选 → 合作 brief → 内容复写 → 数据复盘 → 投放监测 → 线索挖掘」的运营 Agent。

**文档**：[PRD](docs/PRD.md)（产品需求：思考机制、功能域、非功能指标、已知局限）　｜　[使用指南](docs/USAGE.md)（从零跑通 → 接企微/飞书/第三方数据）　｜　[接库指南](docs/DATASOURCE.md)（接企业数据库）　｜　行为评测 `python eval/run_eval.py`

它最重要的特性不是能做什么，而是**做不了的时候会说做不了**。

---

## 关于数据

| 项 | 说明 |
|---|---|
| 商品销售表 | 列结构照抖音电商罗盘「商品详情-销售分布」导出格式，**数值为合成** |
| 候选达人池 | 60 位，合成 |
| 投放执行数据 | 12 位达人 × 14 天，合成；刻意埋了两类异常用于演示监测 |
| 真实文件可用 | 解析器支持该导出格式的 `.xls`，`--sales` 指向你的文件即可 |
| 未使用 | 任何公司内部经营数据、真实达人信息或投放策略 |

**这份导出有个真坑**：所有指标都是区间值（`销量 5000-1w`、`转化率 5%-10%`）。`float()` 直接崩，取中点又会让误差叠加——所以 `parse_range()` 和「客单价置信度」是这个项目的一等公民，不是附属功能。

---

## 这个 Agent 怎么「思考」

不是脚本，也不是套壳网页。给定一句自然语言目标后，模型自己决定做什么：

```
① PLAN     先写 3–6 步执行计划，并声明「还缺什么信息」——只给计划，不给答案
② ACT      带 14 个工具的 JSON Schema 做 function calling，自己选工具、自己传参数
③ OBSERVE  工具返回的事实回灌进上下文（单条截断 2400 字符，防超窗）
④ REPAIR   参数不合法 → 把可接受参数回给模型，同一调用只重试一次
⑤ REFLECT  模型准备作答时，强制自检一次：
            «每个数字都对得上工具返回吗？有没有该查没查的？有没有该拒绝而你没拒绝的？»
            → 发现问题就回去补查，确认无误才输出
⑥ FINAL    判断依据（带数字）→ 结论/名单 → 风险与待人工确认项
```

**一次真实运行里自检抓到什么**（trace 可回放，见 `traces/`）：

> 模型在第 9 步自查时自己列出三个问题：
> 1. 「差 5–7 倍」是我自己算的派生值，不是工具返回，需标注；
> 2. 用户要「起量」，我给了名单却**没跑监测、没跑复盘**，这两项影响预算该集中还是分散；
> 3. `allocate_budget` 已提示「预算只用掉 8%、池子已选完」，我不该仍然输出看似完整的方案，**正确做法是先扩池或明确拒绝**。
>
> 然后它自己回头补调了 `review_campaign` 与 `monitor_scan`。

这类行为不是靠规则写出来的，是模型按 system prompt 里的五条硬原则现场判断的。

**配套机制**

| 机制 | 作用 |
|---|---|
| 并行 tool_calls 补回执 | 模型一轮返回多个调用时逐个执行，每个 `tool_call_id` 都补 tool 消息，否则 OpenAI/DeepSeek 协议直接报 400 |
| 上下文压缩 | 累计字符超 40,000 时，把更早的 tool 回执压成摘要（最近 8 条保留完整），长任务不撑爆窗口 |
| 触顶收尾 | 步数或 token 触顶时，再问一次模型「基于已有事实把结论说完」，而不是丢一句占位话 |
| 双上限 | 规划步数 ≤ 16、token ≤ 150,000、执行步数 ≤ 40 |
| 降级不沉默 | 没配 key 时自动回退规则规划器，并在 UI / `agent_meta` / 结论里写明当前用的是哪个 |
| 用量可观测 | `logs/llm_usage.jsonl` 记账，`/api/llm/status` 实时查 |

**为什么还保留规则规划器**：它是行为基线。11 条评测跑的就是它——有了它，「模型到底有没有比规则做得好」才是可测量的，而不是一句宣传。

---

## 五类能力

### A. 达人筛选与合作

```
parse_product_sales → build_brief → search_candidates → score_candidates → allocate_budget
                                                    ↓
                              negotiation_advice（对比同池 CPM 中位，判断要不要压价）
                              draft_collab_brief（合作 brief：必现要素 / 禁止事项 / 交付要求）
```

评分四维：匹配度 30 / 内容 25 / 转化 30 / 成本 15，批内分位归一化 → S/A/B/C。

### B. 内容复写

先 `compliance_check` 原文，再 `rewrite_content`，最后再 check 一次，**前后两次结果都要报**。

改写约束写死在 system prompt 里：删医疗功效、钩子落具体场景、三段推进、软引导、按平台控字数（小红书 300–500 / 抖音 80–150 / 视频号 120–200）。

### C. 数据复盘

`review_campaign` 按内容类型 / 达人层级 / 单达人聚合 ROI、CTR、CVR、CPM，给出最好与最差分组。
`diagnose_funnel` 把单达人变化拆到 **曝光 / 点击率 / 转化率 / 客单价** 四环，指出掉在哪、该查什么。

### D. 投放监测

`monitor_scan` 滚动比对「近 3 天 vs 前 7 天」，命中规则即告警：

| 规则 | 阈值 | 级别 |
|---|---|---|
| 转化骤降 | −30% | P0 |
| 曝光腰斩 | −45% | P0 |
| 曝光异常飙升 | +50% 且转化未跟上 | P1 |
| CPM 飙升 | +40% | P1 |

---

### E. 可直接发出去的产出

`draft_outreach_message` 生成首次邀约话术（提到对方具体内容方向、说清预算区间、低门槛下一步），
`compose_daily_report` 生成给主管的日报（整体数据 / 要动的告警 / 建议动作 / 需人工确认）。

这两类都不需要人再加工：话术可复制直接发，日报可推送或贴进群。

---

## 线索流水线（群消息 → 达人名单）

运营在群里丢一个账号，系统自动补全、评分、入库、配话术：

```
群消息文本
   ↓ 抽账号（小红书号 / 抖音号 / 主页链接，抽不到就返回空，不猜）
   ↓ 补画像（星火·飞瓜；未配凭证按账号 ID 稳定生成）
   ↓ 四维评分 + 分层（代码算，模型不能改数）
   ↓ 风格拆解（实测型 / 测评对比型 / 生活vlog型 …，各带投放建议）
   ↓ 写飞书多维表格（未配置则落 CSV，字段一致可直接导入）
   ↓ S/A 层自动配货盘 + 话术，进「待发队列」
```

**默认不自动私信达人**——生成待发队列由人确认。原因写在 [使用指南 · 第 9 节](docs/USAGE.md#9-高匹配自动发货盘与话术)：企微没有开放私信陌生人的能力，批量触达既违规又低效。

在界面上粘贴一段群消息即可试，也可以调接口：

```bash
curl -X POST http://127.0.0.1:8765/api/pipeline \
  -H "Content-Type: application/json" \
  -d '{"text":"抖音号：jiuzuo2024 粉丝 12.3w","write":true}'
```

---

## Web 工作台（推荐给运营用）

```bash
python web/server.py
# 浏览器打开 http://127.0.0.1:8765
```

不出意外的话，这是运营同事唯一需要的命令。

**界面分三块**

| 区域 | 内容 | 解决什么 |
|---|---|---|
| 左侧栏 | 5 个常用指令 + 预算输入 + 规划器切换 | 不用记命令行参数，点一下就跑 |
| 驾驶舱 | 待处理告警（P0/P1）、整体 ROI、最优内容类型、客单价与置信度 | 一屏看完今天要不要动手 |
| 结果区 | 入选名单表（可导出 CSV）、告警表、漏斗诊断、复写前后对比、执行轨迹 | 结论直接可执行，不用再翻报告 |

**为「少点几下」做的几个细节**

- 名单每行一个 `Brief` 按钮，点一下把合作 brief 复制到剪贴板，直接发给达人
- 名单可一键导出 CSV，字段对齐投放表
- 告警按 P0/P1 排序，每条都带「查什么」，不是只报数字
- 客单价置信度低时，卡片上直接标注「不用于硬筛选」——避免有人拿 23.3 元去定价格带
- 执行轨迹默认折叠在底部，需要核对数字时再展开

**技术形态**：纯静态文件 + 标准库 `http.server`，零前端构建、零依赖。接口只有四个：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/overview` | 驾驶舱数据（销售结构 / 告警 / 复盘） |
| POST | `/api/run` | 跑一次 agent，返回 trace 与结构化结果 |
| GET | `/api/brief?ids=` | 生成合作 brief（Markdown，可直接发人） |
| GET | `/api/outreach?ids=` | 生成邀约话术（可直接复制发人） |
| GET | `/api/report` | 生成日报（Markdown） |
| POST | `/api/notify` | 推送日报（默认 dry-run，落盘 outbox/） |
| POST | `/api/pipeline` | 群消息 → 线索 → 评分 → 飞书写入 → 待发队列 |
| GET | `/api/export` | 导出上次名单 CSV |
| GET | `/api/datasource` | 当前数据源（csv / sql / http） |
| GET | `/api/llm/status` | 模型是否可用、模型名、累计 token 与延迟 |
| POST | `/api/llm/test` | 连通性自检（未配 key 时明确报错） |
| GET | `/api/last` | 最近一次运行结果（刷新页面不丢） |

`/api/run` 额外返回 `agent_meta`，把 Agent 的思考过程透明化：

```json
{"planner": "llm", "model": "deepseek-chat", "plan": ["1. 先取销售结构…", "2. …"],
 "tokens": 149010, "steps": 10, "llm_available": true, "env_loaded": 3}
```

**界面上的 AI 状态**：顶部一行显示「模型已连接 / 未配置 key（走离线规则）」，旁边是「测试 AI 连接」按钮；跑完一次后展开「模型计划」卡片，能看到它自己写的执行步骤和本次 token 消耗。

---

## 快速开始

### 命令行（批处理 / 定时任务用）

```bash
git clone https://github.com/Fenn12/kol-selection-agent.git
cd kol-selection-agent

# 离线基线（无需 key，四类能力都能跑）
python run_agent.py --goal "全流程跑一遍：指压板新品起量，预算 8000"
python run_agent.py --goal "把这波投放复盘一下"
python run_agent.py --goal "监测一下有没有异常"
python run_agent.py --goal "把这几条文案改写一版"

# 行为评测
python eval/run_eval.py
```

接模型（DeepSeek / 任一 OpenAI 兼容接口），两种配法二选一：

```bash
# 方式一：写 .env（推荐，不会误提交；已加入 .gitignore）
cp .env.example .env
# 编辑 .env 填 DEEPSEEK_API_KEY=sk-xxx

# 方式二：环境变量
export DEEPSEEK_API_KEY=sk-xxx
export DEEPSEEK_BASE_URL=https://api.deepseek.com/v1   # 可选
export MODEL=deepseek-chat                              # 可选
```

然后：

```bash
python run_agent.py --goal "..." --planner llm      # auto 也行：有 key 自动走模型
python eval/run_eval.py --planner llm               # 与规则规划器做对照
```

连通性自检：启动 Web 工作台后点「测试 AI 连接」，或 `curl -X POST 127.0.0.1:8765/api/llm/test`。

零第三方依赖，只用标准库（`urllib` 直连，不引 openai 包）。`.env` 只补不覆盖已有的环境变量。

---

## 接企业内部数据源

业务代码不动，只切一个环境变量：

```bash
KOL_DATASOURCE=csv     # 默认，读 data/*.csv
KOL_DATASOURCE=sql     # 读数据库，SQL 写在 sql/mapping.json
KOL_DATASOURCE=http    # 调内网 API
```

**改 SQL 就能接**：把 `sql/mapping.json` 的查询换成你自己的表，字段名对不上就在 `columns` 里加映射（左侧你的列名，右侧标准名）。

```bash
export KOL_DATASOURCE=sql
export KOL_DB_URL="mysql://reader:pass@10.0.0.12:3306/marketing"
```

驱动不匹配（Oracle / 达梦 / ClickHouse）时，写个模块暴露 `connect()`，用 `KOL_DB_MODULE=my_pkg.kol_db` 挂上去，SQL 写法不用改。

**已经验证可行**：

```bash
python scripts/build_sqlite_demo.py          # 把样例数据灌进 SQLite
KOL_DATASOURCE=sql KOL_DB_URL="sqlite:///data/demo.db" python run_agent.py --goal "起量"
```

同一份数据，CSV 与 SQL 两种来源跑出来结果完全一致（18 步 / 8 人 / 4 条告警）。

完整接入说明见 [`docs/DATASOURCE.md`](docs/DATASOURCE.md)，含数据契约、口径提醒与常见问题。

---

## 定时监测

```bash
python scripts/daily_monitor.py              # 有 P0 才推送
python scripts/daily_monitor.py --always     # 每天都推
python scripts/daily_monitor.py --dry-run    # 不发送，落盘到 outbox/
```

**默认只在有 P0 时推送。** 每天发一封「一切正常」，三周后没人会打开——要发就发需要动手的。

定时方式：

```bash
# Windows 计划任务，每天 9:00
schtasks /create /tn "KOLDailyMonitor" /tr "python D://path//scripts//daily_monitor.py" /sc daily /st 09:00

# Linux / macOS
0 9 * * * cd /path/to/kol-selection-agent && python scripts/daily_monitor.py >> logs/cron.log 2>&1
```

推送没配 SMTP 时不报错，落到 `outbox/`，链路照样能验证。配置见 `agent/notify.py` 顶部注释。

---

## 三个设计决定

### 1. 能算的用代码，要写的用模型

评分、ROI、异常判定全部是确定性代码，**模型不能改数**；只有 brief 与文案走模型。这样即便模型幻觉，也不会把 1.8 的 ROI 说成 3.5。

代价是灵活性下降——模型不能"灵活地重新定义指标"。这个取舍是故意的。

### 2. 监测基线用中位数，不用均值

异常期一旦被算进基线，均值会被自己稀释：曝光翻倍的那几天把基线抬高，导致「涨幅不够」而漏报。

实测中同一份数据，均值基线漏掉了「曝光 +58.7% 但转化 −56%」这个组合，改中位数后命中。**这条是跑出来才发现的，不是设计时想到的。**

### 3. 护栏分两级

| 级别 | 触发 | 行为 |
|---|---|---|
| BLOCK | 工具报错 / 候选池为空 / 预算不可行 / 数据缺失 | 立即停，输出原因与替代方向 |
| WARN | 复写后仍违规 / 高风险工具被调用 / 无告警 | 继续跑，但写进结论的「风险与待确认」 |

---

## Agent 行为评测

`eval/tasks.json` 里 11 条任务，全部是行为断言：

| ID | 测什么 |
|---|---|
| T1 | 选人链路完整，工具顺序正确 |
| T2 | 预算低于最低报价时拒绝 |
| T3 | 筛选条件无法满足时说明原因 |
| T4 | 数据文件缺失时第一步就停 |
| T5 | 复盘给出整体 ROI 与最好/最差分组 |
| T6 | 监测命中「转化骤降」与「曝光异常飙升」 |
| T7 | 3 条样本复写后合规问题清零 |
| T8 | 四类能力串跑不中途终止 |
| T9 | 同输入两次运行结论一致 |
| T10 | 日报包含整体数据、P0 清单与建议动作 |
| T11 | 邀约话术非空且含发送前确认项 |

```bash
$ python eval/run_eval.py
通过 11/11 = 100%
```

**这不是模型效果指标**，是行为断言通过率。区别写在这里，免得被误读。

---

## 目录

```
kol-selection-agent/
├── run_agent.py            # CLI
├── agent/
│   ├── llm.py              # OpenAI 兼容客户端：重试 / JSON / token 记账
│   ├── datasource.py       # 数据源抽象：csv / sql / http
│   ├── notify.py           # 推送：SMTP，未配置则落盘
│   ├── env.py              # .env 加载（只补不覆盖）
│   ├── integrations.py     # 企微 / 星火飞瓜 / 飞书 三个适配器
│   ├── pipeline.py         # 线索流水线：抽取→画像→评分→写表→话术
│   ├── core.py             # 区间解析、商品简报、评分、预算分配
│   ├── tools_extra.py      # 合作 brief、谈判、复写、复盘、监测、邀约、日报
│   ├── registry.py         # 14 个工具的 schema 与 handler
│   ├── planner.py          # LLM 规划器（plan/act/repair/reflect/压缩/收尾）+ 规则规划器
│   └── runner.py           # 执行、护栏、trace
├── web/                    # 本地 Web 工作台（零依赖）
│   ├── server.py           # 11 个接口 + 静态文件服务
│   └── static/             # index.html / style.css / app.js
├── sql/                    # 企业库对接：mapping.json / schema_enterprise.sql
├── scripts/                # build_sqlite_demo.py / daily_monitor.py
├── docs/
│   ├── PRD.md              # 产品需求文档（思考机制 / 需求清单 / 指标 / 局限）
│   ├── USAGE.md            # 使用指南（从零跑通 → 接企微/飞书）
│   └── DATASOURCE.md       # 接库指南（三种方式 + 数据契约）
├── data/                   # 全部合成：销售分布 / 候选池 / 投放数据 / 待复写样本
├── eval/                   # 11 条行为评测
└── logs/                   # token 记账（gitignore）
```

每次运行会把 trace 写到 `traces/*.json`，可逐步回放。

---

## 已知局限

1. **自检只触发一次**：REFLECT 在模型第一次准备作答时注入，整个任务内只做一轮。实测能抓出"该查没查""该拒绝没拒绝"，但若补查后又产生新问题，不会再自查第二遍。
2. **离线规划的意图识别是关键词匹配**：复合指令（如"先复盘再改文案"）可能识别不全。
3. **候选池仅 60 人**：分位归一化在小样本下排序不稳，真实使用应扩到百人以上。
4. **评分不含内容语义**：内容质量用互动率、爆文率等代理指标，没做语义理解。
5. **监测阈值未经真实数据校准**：50% / 30% 这些数字来自经验，换品类需重标。
6. **未接平台 API**：达人数据与投放数据需由调度或人工导入（数据源层已留出 HTTP 接口）。
7. **数据源整源切换**：目前 csv/sql/http 三者互斥，不能部分数据集走库、部分走本地。
8. **企微读聊天记录需企业侧配合**：群机器人只能发不能收；读消息需自建应用回调（要公网地址）或会话存档（要服务商 SDK）。所以默认提供粘贴导入把链路跑通。
9. **星火/飞瓜默认走 mock**：两家无免费公开 API，凭证未配时按账号 ID 稳定生成假数据，字段结构与真实接口对齐，便于先验证链路。

---

## 许可

MIT。
