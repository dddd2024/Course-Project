# V1 设计文档：未知二进制协议推断与加密流量行为分析

> Status: **Design Baseline V1**  
> Purpose: 作为后续开发、分工、接口评审和实验设计的第一版权威设计基线。

## 1. 课题目标

面向来源未知或协议结构尚不明确的 `.dat` 二进制网络数据，构建一套可解释、可验证、可复现的分析流水线。系统结合传统统计分析、协议逆向工程方法、机器学习和大模型语义推理，完成：

1. 二进制比特/字节流特征分析；
2. 数据包边界识别；
3. 相似数据包聚类与对齐；
4. 数据包统计特征分析；
5. 协议字段结构与字段语义推断；
6. 可恢复明文、未加密字段和受控测试数据的还原；
7. 基于长度、方向、时间和 burst 等信息的数据访问行为分析；
8. 访问行为类型识别；
9. 输出机器可读协议 schema、解析结果、置信度和证据。

最终验收输入以 `.dat` 为核心，同时允许使用 PCAP 作为开发和对照数据来源。

## 2. 明确边界与非目标

### 2.1 本项目做什么

- 推断未知二进制流中可能存在的数据包边界；
- 发现固定字段、枚举字段、长度字段、序号、时间戳、校验字段和 payload 等候选；
- 对高熵区域进行“可能加密/压缩”的统计判断；
- 在持有测试密钥的自生成数据集上进行受控解密和还原验证；
- 对加密流量利用 packet size、direction、inter-arrival time、burst、flow ratio 等侧信息做行为建模；
- 让 LLM 负责提出语义假设，但由确定性程序负责验证关键结论。

### 2.2 本项目不做什么

- 不声称在没有密钥时破解 AES-GCM、ChaCha20-Poly1305、TLS 1.3 等现代加密；
- 不以真实未授权目标为实验对象；
- 不把“LLM 看十六进制后猜协议”作为唯一分析方法；
- 不以训练一个新的大规模基础模型作为课程阶段的主要工作量。

## 3. V1 核心思想

V1 采用 **LLM-guided, Evidence-verified Unknown Protocol Inference**：

```text
Raw Binary Data
      |
      v
Deterministic / Statistical Analysis
      |
      v
Boundary + Alignment + Field Candidates
      |
      v
LLM Semantic Hypothesis
      |
      v
Deterministic Constraint Verifier
      |
  +---+---+
  |       |
ACCEPT  REJECT/UNSURE
  |       |
  |       +------> revise hypothesis / try alternative interpretation
  v
Protocol Schema + Confidence + Evidence
```

核心原则是：**模型可以提出假设，但模型本身无权把未经验证的假设升级为事实。**

## 4. 总体架构

```text
unknown.dat / pcap
        |
        v
[1] Input Normalization
        |
        v
[2] Statistical & Byte-Level Analyzer
    - byte frequency
    - Shannon entropy
    - local entropy
    - printable / zero ratio
    - n-gram
    - autocorrelation / periodicity
        |
        v
[3] Packet Boundary Detector
    - repeated-prefix evidence
    - entropy transition
    - candidate length consistency
    - alignment gain
        |
        v
[4] Message Cluster & Alignment
        |
        v
[5] Field Inference
    - constant / magic
    - enum / message type
    - length
    - sequence
    - timestamp
    - checksum
    - variable payload
        |
        v
[6] LLM Protocol Reasoner
        |
        v
[7] Evidence Verifier
        |
        +----------------------+
        |                      |
        v                      v
[8A] Protocol Schema      [8B] Behavior Features
        |                      |
        v                      v
Kaitai / JSON Export     ML / Rule Classifier
        |                      |
        v                      v
Structured Restore      Behavior Type + Confidence
```

## 5. 模块设计

### 5.1 Input Normalization

职责：把 `.dat` 和 PCAP 输入统一为内部 `ByteStream` / `MessageSample` 表示。

V1 要求：
- `.dat` 以原始 bytes 读取；
- PCAP 可通过 Scapy 提取 transport payload；
- 保留 source id、offset、direction、timestamp（如果可获得）；
- 不在这一层做协议语义猜测。

### 5.2 Statistical & Byte-Level Analyzer

至少计算：
- 全局 Shannon entropy；
- 滑动窗口 local entropy；
- byte frequency；
- printable byte ratio；
- zero-byte ratio；
- n-gram 高频模式；
- 重复前缀/后缀；
- 自相关或周期性特征；
- 可选 compression ratio。

输出为结构化特征，不直接输出“这就是某协议”的结论。

### 5.3 Packet Boundary Detector

目标：在不知道 framing 的情况下生成候选分包位置。

V1 建议评分：

```text
BoundaryScore(x) =
    a * prefix_repeat
  + b * length_consistency
  + c * entropy_transition
  + d * alignment_gain
  + e * field_stability
```

每个候选边界必须包含：offset、score、evidence。后续聚类/字段推断可反向调整边界置信度。

### 5.4 Message Clustering & Alignment

目标：把结构相似的数据包聚成若干 message family，并在每一族内部对齐字段。

V1 可直接复用/参考 Netzob 的协议格式推断能力，并保留自研 adapter，使上层不依赖 Netzob 的内部对象模型。

输出：
- cluster id；
- aligned messages；
- stable/variable regions；
- alignment confidence。

### 5.5 Field Inference

字段候选包括：
- magic / constant；
- version；
- message type / enum；
- packet/payload length；
- sequence number；
- timestamp；
- checksum；
- payload；
- unknown。

BinaryInferno 可作为字段推断 baseline/参考实现，但项目自己的统一输出结构必须独立。

### 5.6 LLM Protocol Reasoner

LLM 不直接接收无限制原始十六进制，而优先接收经过预处理的 evidence：

```text
Field A: offset=0, len=2, constant=A55A, repeat=99.8%
Field B: offset=2, len=1, unique_values=3
Field C: offset=3, len=2, correlation_with_packet_length=0.997
Field D: offset=5, variable, entropy=7.92
```

LLM 输出必须是结构化 hypothesis，例如：

```json
{
  "field": "length",
  "offset": 3,
  "size": 2,
  "endian": "big",
  "confidence": 0.82,
  "reason": "strong correlation with observed packet length"
}
```

### 5.7 Deterministic Evidence Verifier

这是 V1 的重点模块之一。

例：LLM 判断 `offset 3..4` 是 big-endian length，验证器应在所有样本上测试至少这些解释：
- field == full packet length；
- field == payload length；
- field + constant header size == packet length；
- big endian / little endian。

只有达到设定阈值的假设才能被标记为 `accepted`。其余为 `rejected` 或 `uncertain`。

同理验证：
- sequence 是否单调/近似单调；
- timestamp 是否落在合理范围并呈时间顺序；
- checksum 是否与候选数据区匹配；
- enum 是否呈小规模离散集合；
- magic 是否在推断边界处稳定出现。

### 5.8 Protocol Schema / Parser Export

当字段结构达到足够置信度后，输出：
- JSON schema（项目内部标准）；
- 可选 Kaitai Struct `.ksy`；
- 由 schema 驱动的解析结果；
- 每个字段的 confidence/evidence。

理想演示链：

```text
unknown.dat
 -> inferred schema
 -> generated parser
 -> parse the same data again
 -> structured records
```

### 5.9 Traffic Behavior Analysis

对于无法查看 payload 内容的加密流量，主要使用：
- packet size sequence；
- direction sequence；
- inter-arrival time；
- burst size / burst length；
- upstream/downstream byte ratio；
- duration；
- packet count；
- flow statistics。

V1 行为类型建议使用可控、可解释的五类：
- `QUERY`
- `DOWNLOAD`
- `UPLOAD`
- `HEARTBEAT`
- `STREAM`

先实现规则/RandomForest baseline，有余力再接入 NetMamba、YaTC 或其他深度模型。

## 6. 开源组件使用原则

V1 计划：

- **Scapy**：PCAP 和 packet payload 预处理；
- **NFStream**：flow 统计特征；
- **Netzob**：message format inference / alignment baseline；
- **BinaryInferno**：binary field inference baseline/reference；
- **Kaitai Struct**：协议 schema 到 parser 的导出；
- **scikit-learn**：RandomForest 等行为分类 baseline；
- **NetMamba / YaTC / ET-BERT**：可选高级实验，不作为首个可运行版本的阻塞依赖。

原则：开源项目用于成熟能力和 baseline，项目自己的核心价值集中在统一流水线、边界推断、证据化语义推断、验证、置信度和系统评测。

## 7. V1 内部数据对象

建议统一以下核心对象：

### PacketCandidate
- `start_offset`
- `end_offset`
- `boundary_confidence`
- `boundary_evidence`
- `direction`（可选）
- `timestamp`（可选）

### FieldHypothesis
- `name`
- `offset`
- `size`
- `semantic_type`
- `endian`
- `model_confidence`
- `evidence`

### VerificationResult
- `hypothesis_id`
- `status: accepted | rejected | uncertain`
- `score`
- `tests`
- `support_count`
- `sample_count`

### BehaviorPrediction
- `flow_id`
- `label`
- `confidence`
- `features`

## 8. 测试数据设计

至少建立三组自生成 ground-truth 数据：

### Dataset A — Plain Binary Protocol
Header 与 payload 都为明文，用于验证分包、字段语义和数据还原。

### Dataset B — Plain Header + Encrypted Payload
Header 保留 magic/type/length/seq 等结构，payload 使用受控测试密钥加密。系统在不知道 schema 时推断结构；评测程序持有 ground truth 和 key。

### Dataset C — Multiple Message Types + Encrypted Payload
包含多种 message type、不同长度、不同访问行为，用于同时验证 clustering、field inference 和 behavior classification。

ground truth 与分析输入必须分离，避免算法直接读取答案。

## 9. 实验设计

### 9.1 Baseline

- Baseline A：纯统计/启发式；
- Baseline B：Netzob / BinaryInferno 类现有结构推断；
- Proposed：统计 + alignment + LLM hypothesis + deterministic verifier。

行为分类另设：
- rules / RandomForest；
- 可选 NetMamba/YaTC/ET-BERT。

### 9.2 指标

- Packet Boundary Precision / Recall / F1；
- Field Boundary F1；
- Field Semantic Accuracy；
- Restoration Accuracy；
- Behavior Classification Precision / Recall / F1；
- False Hypothesis Rate；
- Verification rejection/correction rate；
- processing time；
- optional token/cost metrics。

### 9.3 Ablation

至少考虑：
- w/o LLM；
- w/o deterministic verifier；
- w/o alignment；
- w/o local-entropy features。

其中最关键的对比是：`LLM only` vs `LLM + verifier`，用于证明证据验证能否减少错误字段语义。

## 10. 数据集切分原则

流量分类不得简单随机拆同一 flow 的 packet 到 train/test。应至少按 flow 划分；有条件时按 capture session/day 划分，减少数据泄漏和伪相关。

## 11. V1 验收最小闭环

V1 最低可演示闭环：

1. 上传/指定一个 `.dat`；
2. 显示 entropy、byte distribution、重复模式；
3. 输出候选 packet boundaries；
4. 对包进行 clustering/alignment；
5. 推断 magic/type/length/seq/payload 等字段候选；
6. LLM 提出字段语义；
7. verifier 输出 ACCEPT/REJECT/UNSURE 与证据；
8. 生成 JSON schema；
9. 用 schema 重新解析 `.dat`；
10. 对有方向/时序信息的数据输出 behavior type 与 confidence。

## 12. V1 完成标准

只有同时满足以下条件，V1 才算完成：

- 从 `.dat` 到结构化输出的端到端流程可重复运行；
- 核心结果带 confidence 与 evidence；
- 至少存在一组 ground-truth 自生成测试数据；
- 至少完成一组 baseline 对比；
- LLM 推断不绕过 verifier；
- 文档中明确现代加密不可在无密钥条件下被系统“破解”；
- 测试、设计、安装和使用说明能够支持另一名组员独立复现。

## 13. 后续版本候选

V1 完成后再考虑：
- 更强的自动 framing；
- 多协议混合流自动拆分；
- state-machine inference；
- active learning / confidence-driven analysis；
- NetMamba/YaTC 等深度流量表示；
- Web UI；
- 自动 Kaitai parser validation；
- 更严格的跨数据集泛化实验。

这些内容不应阻塞 V1 的端到端闭环。
