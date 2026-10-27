# KOL Selection Agent

> **English abstract** — A tool-using agent that turns a product's sales-distribution export into an executable KOL outreach plan. It parses platform exports where every metric is a **range** (`5000-1w`, `5%-10%`), derives channel structure and per-creator efficiency, screens a candidate pool on four dimensions, then allocates budget by value-for-money — and **refuses** when budget is short, candidates are empty, or data is missing. Includes a 6-task behavioural eval.

给它一张商品销售分布表和一个预算，它输出一份可执行的达人投放名单；条件不满足时它会说「做不了」，而不是编一份名单。

---

## 关于数据

| 项 | 说明 |
|---|---|
| 商品销售表 | **列结构照抖音电商罗盘「商品详情-销售分布」导出格式**，数值为合成 |
| 候选达人池 | 60 位，全部合成 |
| 真实文件可用 | 解析器支持该导出格式的 `.xls`，把 `--sales` 指向你自己的文件即可 |
| 未使用 | 任何公司内部经营数据、真实达人信息或投放策略 |

**为什么要强调这一点**：这份导出有个坑——**所有指标都是区间**（`销量 5000-1w`、`转化率 5%-10%`）。直接 `float()` 会崩，取中点又会让误差叠加。这个仓库把这件事当成一等问题处理（见下文）。真实表结构 + 合成数值，既保住了方法真实性，又不泄露业务数据。

---

## 它到底做了什麼

```
商品销售分布 (.xls/.csv)
        │
        ▼
[1] parse_product_sales   解析区间值 → 渠道结构 / 人均产出 / 客单价(带置信度)
        │
        ▼
[2] build_brief           主推打法 / 达人类型配比 / 价格带 / 内容红线
        │
        ▼
[3] search_candidates     按平台·粉丝量·报价·是否做过该品类检索
        │
        ▼
[4] score_candidates      匹配度30 / 内容25 / 转化30 / 成本15 → S/A/B/C
        │
        ▼
[5] allocate_budget       按性价比在预算内选人；不够就明确拒绝
        │
        ▼
    名单 + 理由 + 预算使用情况（全程 trace 落盘）
```

---

## 快速开始

```bash
git clone https://github.com/Fenn12/kol-selection-agent.git
cd kol-selection-agent

# 离线基线，无需 API key
python run_agent.py --task "指压板新品起量" --budget 8000

# Agent 行为评测（6 条）
python eval/run_eval.py

# 用自己的真实导出文件（.xls 需 pip install xlrd==1.2.0）
python run_agent.py --sales "D:/你的导出.xls" --budget 8000
```

无第三方依赖（仅标准库）。接模型时任一 OpenAI 兼容接口均可：

```bash
export OPENAI_API_KEY=sk-xxx
export OPENAI_BASE_URL=https://api.openai.com/v1
python run_agent.py --budget 8000 --planner llm
```

---

## 两个规划器，一套护栏

| | `LLMPlanner` | `ScriptedPlanner` |
|---|---|---|
| 谁决定调哪个工具 | 模型（function calling） | 固定顺序，参数取自上一步观察 |
| 用途 | 真实 agent | 离线基线 / 评测对照组 |
| 是否需要 key | 是 | 否 |

**两者共用同一套工具和同一套 `guard()` 护栏**——遇到报错、空池、预算不足一律停下。这样即使模型想硬凑，也过不了护栏。

> 实测状态说明：`ScriptedPlanner` 路径有 6/6 自动化测试覆盖；`LLMPlanner` 代码已实现，但**未纳入本仓库的自动化测试**（需要 API key）。这条写在这里，不藏在脚注。

---

## 三个真实的坑（都在这份代码里处理了）

### 1. 区间值不能直接算

平台导出里 `销量=5000-1w`、`转化率=5%-10%`。`float()` 会直接报错；强行取中点会让下游指标系统性失真。

`parse_range()` 处理了 `0-250` / `5000-1w` / `10w-25w` / `5%-10%` 四种形态，并把「取中值」这件事显式标注在返回值里。

### 2. 客单价由两个区间相除，误差会放大

`客单价 = 销售额中值 / 销量中值` —— 两个 ±50% 的区间相除，结果可能偏得很远。

代码里给客单价加了**置信度**（由两个区间的相对宽度算出）。置信度低时，**不拿它当硬筛选条件**，否则会把候选池筛空。样例数据跑出来客单价 23.3 元、置信度「低」，于是 agent 选择「不锁价格带，只要求品类经验」——这是一个真实的判断，不是配置。

### 3. 预算是硬约束，不是建议

预算低于最低报价时，`allocate_budget` 返回 `feasible: false` 并给出最低预算要求，而不是「挑几个最便宜的凑一凑」。同理，预算只用掉 30% 时会提示原因（池子里便宜的好达人已选完），而不是假装任务完成。

---

## Agent 行为评测

`eval/tasks.json` 里 6 条任务，全部是**行为断言**，不看文案质量：

| ID | 测什么 |
|---|---|
| T1 | 正常场景能给出可执行名单 |
| T2 | 预算低于最低报价时必须拒绝，不许硬凑 |
| T3 | 筛选条件无法满足时说明原因并给替代方向 |
| T4 | 数据文件缺失时第一步就停，不许用默认值编数据 |
| T5 | 同输入两次运行结论完全一致 |
| T6 | 工具调用顺序合法，不许跳步直接给名单 |

```bash
$ python eval/run_eval.py
通过 6/6 = 100%
```

**为什么这样设计**：一个能说会道但会编造达人的 agent，比一个说话笨拙但会拒绝的 agent 危险得多。内容质量可以人工兜底，行为错误不行。

---

## Trace：每一步都留痕

每次运行会把完整 trace 写到 `traces/*.json`：

```json
{
  "task": "指压板新品起量",
  "planner": "scripted",
  "steps": 5,
  "trace": [
    {"step": 1, "thought": "...", "tool": "parse_product_sales",
     "args": {}, "elapsed_ms": 2, "observation": {"销售额_中值": 175000, "...": "..."}}
  ],
  "final": "..."
}
```

面试时可以直接按 trace 回放：每步为什么这么走、看到了什么、在哪一步决定停。

---

## 目录

```
kol-selection-agent/
├── run_agent.py            # CLI 入口
├── agent/
│   ├── core.py             # 区间解析 + 5 个工具 + 评分 + 预算分配
│   └── loop.py             # 两个规划器 + 护栏 + trace
├── data/
│   ├── product_sales.sample.csv   # 列结构照真实导出，数值合成
│   └── candidates.csv             # 60 位合成达人
└── eval/
    ├── tasks.json          # 6 条行为任务
    └── run_eval.py         # 评测执行器
```

---

## 已知局限

1. **LLM 规划器未做端到端测试**：只验证了离线基线。接模型后需要重新跑一遍 `eval/run_eval.py`，并把 `planner` 换成 llm 做对照。
2. **评分维度偏数据、不看内容**：达人的内容质量只用了互动率、爆文率等代理指标，没有做内容语义判断。
3. **候选池只有 60 人**：分位归一化在小样本下排序不稳定，真实使用应扩大到百人以上。
4. **未接平台 API**：达人数据需人工导入，没有做实时拉取与报价校准。
5. **合规只覆盖硬红线**：禁用词与功效表述有拦截，但内容创意层面的合规仍需人工终审。

---

## 许可

MIT。
