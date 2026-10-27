# KOL Operations Agent

> **English abstract** — A tool-using agent covering the full creator-marketing loop: creator selection → outreach brief → content rewriting → performance review → live monitoring. Twelve tools, two planners (LLM function-calling / offline rule baseline), and a guard layer that makes the agent **refuse** instead of fabricate when data is missing, budget is short, or candidates are empty. Nine behavioural evals.

一个覆盖「达人筛选 → 合作 brief → 内容复写 → 数据复盘 → 投放监测」的运营 Agent。

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

## 四类能力

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

## 快速开始

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

接模型（DeepSeek / 任一 OpenAI 兼容接口）：

```bash
export DEEPSEEK_API_KEY=sk-xxx
export DEEPSEEK_BASE_URL=https://api.deepseek.com/v1   # 可选
export MODEL=deepseek-chat                              # 可选
python run_agent.py --goal "..." --planner llm
python eval/run_eval.py --planner llm
```

零第三方依赖，只用标准库（`urllib` 直连，不引 openai 包）。

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

`eval/tasks.json` 里 9 条任务，全部是行为断言：

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

```bash
$ python eval/run_eval.py
通过 9/9 = 100%
```

**这不是模型效果指标**，是行为断言通过率。区别写在这里，免得被误读。

---

## 目录

```
kol-selection-agent/
├── run_agent.py            # CLI
├── agent/
│   ├── llm.py              # OpenAI 兼容客户端：重试 / JSON / token 记账
│   ├── core.py             # 区间解析、商品简报、评分、预算分配
│   ├── tools_extra.py      # 合作 brief、谈判、复写、复盘、监测
│   ├── registry.py         # 12 个工具的 schema 与 handler
│   ├── planner.py          # LLM 规划器 + 离线规则规划器
│   └── runner.py           # 执行、护栏、trace
├── data/                   # 全部合成：销售分布 / 候选池 / 投放数据 / 待复写样本
├── eval/                   # 9 条行为评测
└── logs/                   # token 记账（gitignore）
```

每次运行会把 trace 写到 `traces/*.json`，可逐步回放。

---

## 已知局限

1. **LLM 规划器未做端到端验证**：本仓库的自动化测试只覆盖离线规则规划器。接入 key 后请先跑 `eval/run_eval.py --planner llm` 做对照，再用于生产。
2. **离线规划的意图识别是关键词匹配**：复合指令（如"先复盘再改文案"）可能识别不全。
3. **候选池仅 60 人**：分位归一化在小样本下排序不稳，真实使用应扩到百人以上。
4. **评分不含内容语义**：内容质量用互动率、爆文率等代理指标，没做语义理解。
5. **监测阈值未经真实数据校准**：50% / 30% 这些数字来自经验，换品类需重标。
6. **未接平台 API**：达人数据与投放数据均需手动导入。

---

## 许可

MIT。
