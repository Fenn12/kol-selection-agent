# RAG 与 MCP 实证

> 目标：给「Agent 搭建能力」补上可运行、可复现的工程证据，而不是只写在技能栏。
> 两个能力都不依赖大模型 API：BM25 检索与 MCP Server 都能离线跑。

---

## 1. RAG（BM25 知识库）

### 架构
```
data/knowledge/*.md   →  按二级标题切块（200–400 字）
                      →  中文单字 + 相邻双字（双字加权）分词
                      →  BM25（k1=1.5, b=0.75）
query ───────────────→  top-k 片段  →  注入 rewrite_content 提示词
                      →  结果里回传 rag_hits，前端展示「知识库依据」
```

### 知识库
| 文档 | 内容 |
|---|---|
| `brand_voice.md` | 品牌语气、开头、卖点推进、结尾、禁用表达 |
| `compliance_rules.md` | 极限词、医疗功效、替代医疗、硬引导、疗效时间、平台字数 |
| `kol_selection.md` | 四维评分权重、S/A/B/C 分层、预算贪心、口径 |
| `content_playbook.md` | 三平台长度、结构、改写动作、验收 |
| `case_notes.md` | K040 漏斗、K013 曝光、预算只用 7%、客单价置信度 |

### 接口
```bash
curl "http://127.0.0.1:8765/api/knowledge/search?q=极限词有哪些&k=3"
curl "http://127.0.0.1:8765/api/knowledge/docs"
```

### 评测
`eval/rag_eval.py`：10 条固定 query，检查期望文档是否出现在 top-3。

```bash
python eval/rag_eval.py
```

实测结果（2026-10-27）：

| 指标 | 结果 |
|---|---|
| Recall@3 | **10/10 = 1.00** |
| MRR | **0.95** |
| 语料 | 5 篇文档 / 28 个块 |
| 依赖 | 0（标准库） |

典型命中：
- 「极限词有哪些」→ `compliance_rules`（score 16.69）
- 「S/A/B/C 分层标准」→ `kol_selection` + `case_notes`
- 「K040 转化率骤降怎么查」→ `case_notes` + `kol_selection`

### 接入点
`agent/tools_extra.py::rewrite_content()` 在调用模型前检索 top-3，把片段注入提示词；返回值新增：

```json
{"rag_hits": [{"doc": "content_playbook", "title": "平台要求", "score": 26.34}]}
```

前端「内容复写」结果里展示「知识库依据：content_playbook / compliance_rules」。

---

## 2. MCP Server（stdio）

### 协议
- JSON-RPC 2.0，stdio，一行一个 JSON 对象
- 支持 `initialize` / `notifications/initialized` / `tools/list` / `tools/call` / `ping`
- 协议版本：`2024-11-05`

### 工具
| 工具 | 作用 |
|---|---|
| `search_knowledge` | RAG 检索品牌语气、合规规则、评分与预算方法 |
| `score_candidates` | 60 位候选四维评分 + 分层 + 预算分配 |
| `monitor_scan` | 近 3 天 vs 前 7 天中位数基线，返回 P0/P1 |

### 启动
```bash
python mcp/server.py
```

### 客户端冒烟
`scripts/mcp_smoke.py` 会真实拉起 server，走完 `initialize → tools/list → tools/call × 3`：

```bash
python scripts/mcp_smoke.py
```

实测输出（2026-10-27）：

```json
{
  "ok": true,
  "server": {"name": "kol-ops-mcp", "version": "0.1.0"},
  "protocol_version": "2024-11-05",
  "tools": ["search_knowledge", "score_candidates", "monitor_scan"],
  "search_hits": 3,
  "search_top": "content_playbook",
  "scored": 60,
  "picked": 8,
  "spent": 560.0,
  "alerts": 4
}
```

### 文件
- `mcp/server.py`：协议处理 + 3 个工具
- `scripts/mcp_smoke.py`：stdio 客户端与断言
- `mcp_smoke_out.json`：完整握手 transcript

---

## 3. 和 JD 的对应

| JD 要求 | 这份实证 |
|---|---|
| 字节 AI 策略产品：PE 调试 / Vibe coding / 工作流 / Agent Harness 评估 | RAG 检索 + 复写注入；MCP 工具编排；11 条 Agent 评测 |
| 字节 AI Agent 开发：工具调用 / 评测 / Tracing / MCP | stdio MCP Server 3 工具 + 客户端握手；trace 落盘 |
| 小红书/美团运营：数据 + AI 提效 | 知识库把品牌语气/合规/选人 SOP 变成可检索资产 |

---

## 4. 已知边界

- BM25 不是语义检索：同义改写的召回会下降；下一步可加 embedding 或混合检索。
- MCP Server 目前是 stdio，本地进程用；没有做 SSE/HTTP transport。
- 工具只有 3 个，未覆盖全部 14 个内置工具；可按同样方式继续暴露。
- LLM Key 失效时，改写会回退到离线规则；RAG 检索与 MCP 协议测试不依赖模型，仍可复现。
