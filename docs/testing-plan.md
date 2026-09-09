# Testing Plan V1

## 1. Test Layers

### Unit Tests
验证每个模块自己的确定性行为：
- entropy / frequency / n-gram；
- boundary score；
- endian/length verifier；
- sequence/timestamp/enum/checksum verifier；
- feature normalization；
- schema serialization。

### Contract Tests
验证跨 Track / 跨语言接口：
- `contracts/fixtures/*.json` 必须通过对应 JSON Schema；
- fixture 的 task/input/evidence 引用保持一致；
- shared contract 发生变化时必须先更新 fixture，再更新 producer / consumer；
- CI 不依赖真实 LLM key 或老师数据。

### Integration Tests
验证相邻模块 contract：
- loader -> features；
- features -> boundary；
- boundary -> inference；
- inference -> LLM schema；
- LLM hypothesis -> verifier；
- verified fields -> exporter；
- flow features -> behavior classifier；
- sidecar -> desktop fixture consumer。

### End-to-End Tests
从老师提供的 `.dat` 输入到结构化解析输出；当老师同时提供答案、说明、协议 ground truth 或可验证还原结果时，再基于其实际提供内容计算可计算的 accuracy/F1/restoration 指标。

## 2. Data Strategy

### Teacher-provided evaluation data — authoritative course input

课程验收数据由老师提供，因此**开工前不人为制作一个假想的“正式测试数据集”来替代老师数据**。

收到数据后记录：
- local dataset identifier；
- file size and cryptographic hash；
- received date/version；
- permitted redistribution status；
- any teacher-provided labels/ground truth/expected outputs；
- preprocessing applied by the project。

除非明确允许再分发，否则老师原始 `.dat` 文件保持在本地并继续受 `.gitignore` 保护。

Full registration, metadata, answer-isolation, and arrival steps are documented in [teacher-data-ingress.md](teacher-data-ingress.md).

### Synthetic fixtures — engineering only

项目仍可创建很小的 synthetic byte/JSON fixtures，用于：
- 单元测试；
- schema/contract 测试；
- 边界条件；
- verifier 的正反例；
- 前端在真实后端完成前的 fixed-data contract spike。

这些 fixture **不得冒充老师测试结果或论文性能证据**。当前 `contracts/fixtures/` 只用于接口稳定化，不是协议分析 benchmark。

### Optional controlled research data

只有在老师数据不足以完成某个必要的 ablation/verifier 单元实验时，才额外生成受控 synthetic messages，并记录 generator/version/schema/seed。它们用于解释机制，不替代老师提供的最终 `.dat` 验收。

## 3. Protocol Inference Metrics

在 ground truth 实际可获得时优先报告：
- Packet Boundary Precision
- Packet Boundary Recall
- Packet Boundary F1
- Field Boundary F1
- Field Semantic Accuracy
- Restoration Accuracy
- False Hypothesis Rate
- Accepted Hypothesis Precision
- Parse Coverage
- Constraint Satisfaction Rate
- Processing Time

如果老师数据没有提供某项 ground truth，就明确标为 `not evaluable from provided ground truth`，不要自行杜撰标签。

## 4. Behavior Metrics

在存在行为标签时：
- Accuracy
- Macro Precision / Recall / F1
- Confusion Matrix
- per-class F1

训练/测试必须至少按 flow/session 切分，禁止把同一 flow 的 packet 随机拆到 train 与 test 两侧。如果老师只给单一 `.dat` 且没有可用于监督分类的标签，则行为模块输出统计/聚类/候选类型证据，不虚构 supervised accuracy。

## 5. Baselines

### Protocol Baselines
- A: statistical heuristics only
- B: Netzob / BinaryInferno-based structure inference（实际集成哪个以可复现环境为准）
- Proposed: statistical + alignment + LLM hypothesis + deterministic verification + provenance-aware evidence fusion

### Behavior Baselines
- rule-based
- RandomForest（只有在存在合适标签/样本时）
- optional deep traffic representation model（V1 主链稳定之后）

## 6. Ablations

至少保留以下可配置实验开关或等价实验配置：
- disable LLM;
- disable executable verifier;
- disable provenance-aware fusion;
- disable alignment;
- optional disable local entropy。

最关键实验：

```text
LLM only
vs.
LLM + deterministic verifier
vs.
LLM + verifier + provenance-aware evidence fusion
```

比较错误语义假设率、accepted-field precision、coverage 和可计算的字段准确率。

## 7. Reproducibility

每次正式实验记录：
- git commit SHA；
- dataset id/hash/version；
- Python/dependency versions；
- model/provider/model-name（如适用）；
- random seed（如适用）；
- config；
- start/end time；
- metrics JSON；
- failure reason；
- ground-truth availability / unavailable metrics。

## 8. Demo Gate

进入最终演示候选前必须通过：
1. 老师提供的 `.dat` 可以由统一 loader 读入，不需要改源码；
2. 至少一条 deterministic analysis path 在无 LLM/无网络时可运行并给出明确结果或限制；
3. 至少一个 verifier 能对候选 hypothesis 给出可复现的 ACCEPTED/REJECTED/UNCERTAIN 证据；
4. 若行为标签存在，行为分析输出可复现；若不存在，明确展示统计/聚类证据而不是伪造准确率；
5. LLM/可选依赖不可用时系统明确报告降级状态；
6. README 中最小运行步骤由非原作者成员复现一次；
7. Desktop -> sidecar -> result contract 至少通过 fixed fixture 和一次真实老师数据演示链路。
