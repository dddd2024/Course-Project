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

### Integration Tests
验证相邻模块 contract：
- loader -> features；
- features -> boundary；
- boundary -> inference；
- inference -> LLM schema；
- LLM hypothesis -> verifier；
- verified fields -> exporter；
- flow features -> behavior classifier。

### End-to-End Tests
从 `.dat` 输入到结构化解析输出，并与 ground truth 比较。

## 2. Controlled Datasets

### Dataset A: Plain Binary Protocol
用于最基本的 packet/field/restoration ground truth。

### Dataset B: Plain Header + Encrypted Payload
用于验证系统能否在 payload 不可读时仍恢复 header/framing，并在评测端持有测试 key 时确认 payload restoration。

### Dataset C: Multiple Message Types + Behavior Labels
包含 QUERY / DOWNLOAD / UPLOAD / HEARTBEAT / STREAM，支持 clustering 与行为分类。

每份数据至少保留：
- generator version；
- protocol schema ground truth；
- packet boundaries；
- field annotations；
- behavior labels；
- random seed；
- 测试密钥（仅在明确的受控测试目录/运行环境中使用，不提交真实凭据）。

## 3. Protocol Inference Metrics

- Packet Boundary Precision
- Packet Boundary Recall
- Packet Boundary F1
- Field Boundary F1
- Field Semantic Accuracy
- Restoration Accuracy
- False Hypothesis Rate
- Accepted Hypothesis Precision
- Processing Time

## 4. Behavior Metrics

- Accuracy
- Macro Precision / Recall / F1
- Confusion Matrix
- per-class F1

训练/测试必须至少按 flow 切分，禁止把同一 flow 的 packet 随机拆到 train 与 test 两侧。

## 5. Baselines

### Protocol Baselines
- A: statistical heuristics only
- B: Netzob / BinaryInferno-based structure inference
- Proposed: statistical + alignment + LLM hypothesis + deterministic verification

### Behavior Baselines
- rule-based
- RandomForest
- optional deep traffic representation model

## 6. Ablations

至少保留以下可配置实验开关：
- `--disable-llm`
- `--disable-verifier`
- `--disable-alignment`
- `--disable-local-entropy`

最关键实验：

```text
LLM only
vs.
LLM + deterministic verifier
```

比较错误语义假设率与最终字段准确率。

## 7. Reproducibility

每次正式实验记录：
- git commit SHA；
- dataset id/version；
- Python/dependency versions；
- model/provider/model-name（如适用）；
- random seed；
- config；
- start/end time；
- metrics JSON；
- failure reason。

## 8. Demo Gate

进入最终演示分支前必须通过：
1. Dataset A 端到端解析；
2. Dataset B header/framing 推断；
3. 至少一个 verifier 能纠正错误 LLM hypothesis 的固定示例；
4. Dataset C 至少三类行为可稳定区分；
5. 无网络/模型不可用时，统计与 baseline 模块仍可运行并明确报告降级状态；
6. README 中的最小运行步骤由非原作者成员复现一次。
