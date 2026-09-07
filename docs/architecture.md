# Architecture V1

本文档定义 V1 的模块边界和共享接口。多人开发时，模块内部可独立演进，但跨模块输入输出必须保持兼容。

## 1. Package Boundary

```text
src/course_project/
├── io/            # input normalization
├── features/      # byte/statistical features
├── boundary/      # packet boundary candidates
├── inference/     # clustering/alignment/field inference
├── llm/           # semantic hypothesis generation
├── verification/  # deterministic validation
├── behavior/      # flow/behavior features & classifier
├── exporters/     # JSON/Kaitai/parser export
└── models.py      # shared data contracts
```

## 2. Dependency Direction

允许的主依赖方向：

```text
io
 -> features
 -> boundary
 -> inference
 -> llm
 -> verification
 -> exporters

io/features
 -> behavior
```

规则：
- 下游可依赖上游共享对象；
- 上游不得反向 import 下游实现；
- 第三方工具通过 adapter 使用，避免 Netzob/NFStream 对象泄漏到整个项目；
- 所有跨模块对象优先使用 `models.py` 中的数据类或 JSON-compatible dict。

## 3. Shared Contracts

### PacketCandidate

```python
PacketCandidate(
    start_offset: int,
    end_offset: int,
    confidence: float,
    evidence: dict,
    direction: str | None,
    timestamp: float | None,
)
```

### FieldHypothesis

```python
FieldHypothesis(
    field_id: str,
    offset: int,
    size: int | None,
    semantic_type: str,
    endian: str | None,
    confidence: float,
    evidence: dict,
)
```

### VerificationResult

```python
VerificationResult(
    hypothesis_id: str,
    status: str,  # accepted / rejected / uncertain
    score: float,
    support_count: int,
    sample_count: int,
    tests: dict,
)
```

### BehaviorPrediction

```python
BehaviorPrediction(
    flow_id: str,
    label: str,
    confidence: float,
    features: dict,
)
```

## 4. Adapter Contracts

第三方开源工具必须被放在 adapter 边界后面。例如：

```text
Netzob -> inference/netzob_adapter.py -> project-native field/alignment result
NFStream -> behavior/nfstream_adapter.py -> project-native flow feature dict
Kaitai -> exporters/kaitai.py -> .ksy / generated parser artifact
```

这样可以避免某个开源库安装失败或版本变化时整个项目被锁死。

## 5. Error Semantics

模块不应把失败隐藏成空结果。建议统一区分：
- `invalid_input`
- `insufficient_evidence`
- `unsupported_format`
- `dependency_unavailable`
- `inference_failed`
- `verification_failed`

LLM 返回无法解析、缺字段或不符合 schema 时，应标记为失败/不确定，不允许静默补全为 accepted。

## 6. Confidence Policy

所有重要推断结果都使用 `[0, 1]` 置信度，但不同模块的 score 含义必须在文档/代码中说明。V1 不要求全局校准，但禁止把模型主观 confidence 与确定性统计比例混为同一个指标。

建议区分：
- `model_confidence`
- `evidence_score`
- `verification_score`
- `final_confidence`

## 7. Schema Change Rule

修改共享 contract 时：
1. 先更新本文档；
2. 更新 `models.py`；
3. 在 PR 中列出受影响模块；
4. 至少通知/请求 Integration Owner review；
5. 同一 PR 内补充兼容性测试或迁移说明。
