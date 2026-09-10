# Desktop Application Guide

> Status: implementation guidance
> Scope: local desktop workbench for the existing V1/V2 analysis pipeline

本文档定义课程项目桌面端的推荐形态、技术边界和渐进式实施路线。桌面端用于导入授权的 `.dat`、`.bin`、`.pcap` 或 `.pcapng` 数据，展示可复核的分析证据，并通过 Agent 驱动已有分析工具。它不替换 `docs/architecture.md` 定义的协议推断主流水线。

## 1. Product Goal

桌面端应形成以下闭环：

```text
导入数据
  -> 自动探测格式和可用元数据
  -> 执行统计、边界、对齐、字段和行为分析
  -> Agent 汇总结构化结果
  -> 用户从结论跳转到原始偏移和样本
  -> 用户确认或修正候选结构
  -> 重新验证并导出报告或解析规则
```

Agent 负责编排工具、组织证据和解释不确定性。文件解析、统计计算、字段验证和内容还原由确定性程序执行，不能把大段原始二进制直接交给模型猜测。

## 2. Recommended Stack

| 层 | 推荐技术 | 主要职责 |
|---|---|---|
| Desktop shell | Tauri 2 + Rust | 应用生命周期、受控文件访问、任务与 sidecar 管理、事件转发 |
| User interface | React + TypeScript + Vite | 文件入口、任务列表、Hex 视图、统计图、Agent 对话 |
| Analysis engine | Existing Python package | 特征、边界、对齐、协议推断、验证、行为分类和 LLM 编排 |
| Local persistence | SQLite + result files | 任务索引、状态、证据索引、配置和导出物 |
| Large tabular output | Arrow/Parquet when needed | 大规模数据包、消息和特征结果交换 |

V1 首先复用当前 `src/course_project/` Python 实现。只有经过性能分析确认的热点，例如大文件扫描、TCP 重组或高吞吐消息切分，才迁入独立 Rust crate，避免同时维护两套仍在变化的推断算法。

## 3. Component Boundaries

```text
┌──────────────── React + TypeScript ───────────────┐
│ Import │ Tasks │ Packets/Messages │ Hex │ Agent  │
└──────────────────────┬────────────────────────────┘
                       │ typed Tauri commands/events
┌──────────────────────▼────────────────────────────┐
│ Tauri / Rust Core                                 │
│ file grants │ task lifecycle │ sidecar │ storage │
└──────────────┬───────────────────────┬─────────────┘
               │ JSON Lines            │ SQLite/files
┌──────────────▼───────────────────────┐
│ Python Analyzer Sidecar             │
│ existing pipeline │ tools │ LLM     │
└──────────────────────────────────────┘
```

### TypeScript UI

UI 只展示状态并发起有类型的操作，不直接执行 shell 命令，也不自行解释协议。大量二进制内容采用按区间读取和虚拟滚动，不能一次性载入 WebView 内存。

### Tauri/Rust Core

Rust 是桌面的信任边界：

- 校验用户选择的文件和读取范围；
- 创建、取消和恢复分析任务；
- 启停应用自带的 Python sidecar；
- 把 sidecar 进度转换为前端事件；
- 管理结果目录和 SQLite 元数据；
- 避免向 WebView 暴露任意命令执行能力。

### Python Analyzer

Python 保持现有模块边界，并提供面向任务的稳定工具入口：

- `inspect_file`
- `calculate_features`
- `detect_boundaries`
- `align_messages`
- `infer_fields`
- `verify_hypotheses`
- `classify_behavior`
- `extract_payload`
- `export_result`

第三方 PRE、流量和模型工具继续通过 adapter 接入，不把第三方对象暴露给桌面端。

## 4. Proposed Repository Evolution

当前仓库仍以 Python 研究原型为主。开始实现桌面端后，建议逐步增加：

```text
apps/
└── desktop/
    ├── src/                  # React + TypeScript UI
    └── src-tauri/            # Tauri application and Rust commands
contracts/
├── analysis-result.schema.json
├── agent-response.schema.json
└── sidecar-message.schema.json
src/course_project/           # existing Python analysis engine
prompts/                      # versioned Agent prompts when introduced
```

不要为了提前满足目录形式而一次性移动现有 Python 包。桌面 MVP 建立后，再根据打包和工作区工具的实际需要决定是否引入顶层 workspace。

## 5. Data Import and Task Lifecycle

数据入口支持 `.dat`、`.bin`、`.pcap` 和 `.pcapng`。可选附件包括协议描述、受控测试密钥、TLS key log 和已知明文对照。

```text
CREATED -> INSPECTING -> ANALYZING -> VERIFYING -> COMPLETED
    |           |             |           |
    +-----------+-------------+-----------+-> FAILED
                              +--------------> CANCELLED
```

导入时记录原文件路径或受控副本、SHA-256、文件大小、数据来源说明、格式探测结果、可用元数据、分析配置、代码提交 SHA 和模型版本。默认只读处理原文件。真实流量、密钥和还原明文不得自动提交到 Git，也不得写入普通应用日志。

## 6. Sidecar Contract

Python sidecar 建议作为长期子进程运行，通过标准输入和输出交换 JSON Lines。每行是一个完整 JSON 对象，并使用 `protocolVersion` 做兼容性检查。

```json
{"protocolVersion":1,"id":"task-01","method":"analyze","params":{"inputId":"input-01","stages":["features","boundary","inference"]}}
{"protocolVersion":1,"id":"task-01","event":"progress","stage":"boundary","progress":0.42}
{"protocolVersion":1,"id":"task-01","resultRef":"results/task-01/analysis.json"}
```

接口要求：

- stdout 只输出协议消息，诊断日志写入 stderr；
- 每个请求有唯一 `id`，支持取消、超时和失败状态；
- 大块二进制和大表不进入 JSON，只传受控输入标识、偏移、长度或结果引用；
- 前端不得提供任意程序名或自由 shell 参数；
- Rust 把受控 `inputId` 映射到真实文件路径，减少路径注入和越权读取风险。

## 7. Main User Interface

推荐三栏工作台：

```text
┌─ Tasks ───────┬──────── Analysis Workspace ───────┬─ Agent ──────┐
│ sample.dat    │ Overview / Packets / Messages     │ Findings      │
│ analyzing 72% │ Hex / Alignment / Statistics      │ Evidence      │
│ test-02.dat   │ Behavior / Restored Artifacts     │ Follow-up     │
└───────────────┴───────────────────────────────────┴───────────────┘
```

核心视图包括：

1. **Overview**：格式候选、文件哈希、熵、可打印比例、会话数和异常区间；
2. **Packets / Messages**：明确区分捕获记录、网络包、TCP 流和应用消息；
3. **Hex / Alignment**：按偏移高亮字段，比较同类消息的稳定区和变化区；
4. **Statistics / Behavior**：长度、方向、时间间隔、突发、上下行比和行为候选；
5. **Restoration**：分别标识提取、解码、解压、解密和对象重组结果；
6. **Agent**：显示结论、证据、验证、置信度、限制条件和下一步动作。

点击 Agent 证据时必须能定位到对应输入、消息和字节偏移。用户对字段语义的确认作为显式人工证据记录，不能静默覆盖算法结果。

## 8. Agent Response Contract

Agent 回答同时包含人类可读文本和结构化结果：

```json
{
  "answer": "偏移 2-3 可能是大端消息长度字段。",
  "findings": [{
    "findingId": "finding-01",
    "claim": "bytes[2:4] encode the full message length",
    "status": "UNCERTAIN",
    "confidence": {"model": 0.81, "evidence": 0.96, "verification": 0.972},
    "evidenceIds": ["ev-12", "ev-19"],
    "location": {"inputId": "input-01", "offset": 2, "length": 2},
    "validation": "486 of 500 eligible messages satisfy the relation"
  }],
  "limitations": ["14 messages are truncated or violate the candidate relation"],
  "suggestedActions": [{"tool": "align_messages", "label": "Re-align using this length candidate"}]
}
```

回答规则：

- 文件大小、字节值和验证计数是事实；协议含义和行为类型是推断；用户确认是独立证据；
- `model_confidence`、`evidence_score` 和 `verification_score` 不合并成来源不明的单一分数；
- 缺少时间戳、方向、会话元数据或密钥时，明确说明受影响的能力；
- 与 V2 一致，使用 `ACCEPTED`、`REJECTED` 或 `UNCERTAIN`，允许保留未知区域；
- 每个 `ACCEPTED` 字段必须关联可执行验证记录；
- Agent 不得声称无密钥恢复了正确实现的现代加密载荷。

## 9. Collaboration Boundaries

| Work package | Primary scope | Integration dependency |
|---|---|---|
| Desktop UI | `apps/desktop/src/` | generated TypeScript contracts |
| Tauri integration | `apps/desktop/src-tauri/` | sidecar lifecycle and storage |
| Analyzer API | `src/course_project/` sidecar entry | existing analysis modules |
| Contracts | `contracts/`, shared models | reviewed by UI, Rust and AI owners |
| QA/demo | end-to-end fixtures and packaging | sanitized datasets and expected output |

跨语言开发遵循 contract-first：先更新 schema 和示例，再更新生产者、消费者与兼容性测试。PR 必须说明协议版本、受影响模块和迁移方式。

## 10. MVP Delivery Plan

### D0 — Contract Spike

定义 sidecar 请求、进度、错误和结果 schema；用固定假数据贯通 React -> Tauri -> Python -> React，并验证取消、崩溃和错误展示。

### D1 — Read-only Desktop MVP

支持拖入 `.dat`，执行格式、熵、字节统计和字符串分析，展示 Overview 与虚拟化 Hex 视图，Agent 能引用真实偏移。

### D2 — Interactive Inference

展示消息边界、聚类、对齐和字段候选；允许用户接受、拒绝或修正候选；重新执行验证并导出 JSON/Kaitai 结果。

### D3 — Behavior and Controlled Restoration

增加长度、方向和时序行为视图；在受控密钥可用时展示还原结果；区分无法解密、解密失败、解压失败和对象不完整。

### D4 — Packaging and Performance

将 Python analyzer 打包为 Tauri sidecar，构建目标平台安装包并运行端到端测试；根据测量结果决定是否迁移具体热点到 Rust。

## 11. Acceptance Criteria

桌面 MVP 至少满足：

1. 无需用户单独安装 Python 即可启动受控 sidecar；
2. 大文件采用区间读取，UI 不因整文件载入而冻结；
3. 一个受控 `.dat` 样本可从导入运行到结构化结果；
4. 任务进度、取消、失败和 sidecar 异常都有明确状态；
5. Agent 的关键结论可跳转到原始字节证据；
6. 推断结果展示来源、验证计数、置信度和限制；
7. 无网络或 LLM 不可用时，统计和确定性分析仍能运行；
8. 原始敏感数据、测试密钥和还原明文不会进入 Git 或普通日志；
9. CI 验证 TypeScript 构建、Rust 检查、Python 测试和一条 sidecar contract 集成路径。

## 12. First-version Non-goals

- 实时网卡抓包；
- 插件市场或任意第三方脚本执行；
- 为追求全 Rust 而重写尚未稳定的 Python 推断算法；
- 把 Agent 自然语言回答作为协议事实或评测真值；
- 在缺少必要密钥时承诺恢复现代加密协议明文。

上述边界让桌面端首先成为可复现、可解释、可演示的研究工作台，再根据课程周期和真实性能数据扩展。


## 13. 前端模型配置入口

桌面端顶部的“模型设置”用于配置当前会话的 OpenAI 兼容接口：

1. 填写 Base URL；界面接受服务根地址、`/v1` 地址或完整的 `/chat/completions` 地址。
2. 填写服务实际提供的模型或部署名称。
3. 填写 API Key，并选择 JSON 对象模式或仅提示词约束。
4. 保存后，在左侧开启“模型辅助推理”，再运行分析。

API Key 只在 React 表单和 Rust 进程内存中短暂存在。Rust 仅在启动 Sidecar 子进程时通过环境变量注入密钥；Sidecar 协议、任务配置、分析结果、复核导出和日志都不携带密钥。关闭应用后配置消失。更新或清除配置会重启 Sidecar，因此界面会要求重新选择输入文件。

模型模式使用 `evidencegraph` 分析并增加 `llm` 阶段。模型只能生成候选语义假设；确定性验证、来源感知融合和三态决策规则保持不变。关闭模型开关时继续使用离线确定性流程。
