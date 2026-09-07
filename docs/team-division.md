# Team Division V1

本文档把项目拆成可并行推进的 work packages。当前使用角色占位符，不绑定具体姓名；组员确定后，将 `Owner` 替换为真实姓名与 GitHub 用户名。

> 课程要求最终提交任务分工说明，因此每个成员需要保留对应 Issue、PR、测试结果和文档作为工作量证据。

## 1. Suggested 6-Person Allocation

| WP | 建议负责人 | 工作量占比 | 主要范围 | 关键产出 |
|---|---|---:|---|---|
| WP0 | Member A — Integration / Architecture | 15% | 总体架构、共享接口、集成、CLI/入口 | architecture、models、integration PR |
| WP1 | Member B — Binary Analysis | 20% | `.dat` loader、熵/频率/n-gram、packet boundary | feature analyzer、boundary detector、单测 |
| WP2 | Member C — Protocol Inference | 20% | clustering、alignment、Netzob/BinaryInferno adapter、字段候选 | inference pipeline、baseline |
| WP3 | Member D — LLM & Verification | 20% | structured prompt/output、字段语义假设、deterministic verifier | reasoner、verifier、LLM-only 对照 |
| WP4 | Member E — Traffic Behavior / ML | 15% | NFStream/flow features、规则/RandomForest、行为分类 | behavior pipeline、metrics |
| WP5 | Member F — Export / QA / Demo | 10% | JSON/Kaitai export、parser validation、测试数据、报告/演示集成 | exporter、demo dataset、test report |

总计：100%。

如果实际人数不是 6 人，不要机械保持这一人数结构；保持 WP 边界，允许一个人承担多个 WP 或把一个 WP 再拆分。

## 2. Work Package Details

### WP0 — Integration / Architecture

Owner: `TBD`

Responsibilities:
- 维护 `docs/design-v1.md` 与 `docs/architecture.md`；
- 维护共享 `models.py`；
- 定义 pipeline 入口和模块装配方式；
- 处理跨模块冲突；
- 组织集成测试；
- 最终冻结演示版本。

Not responsible for:
- 替其他成员完成其模块内部算法。

### WP1 — Binary Analysis & Boundary Detection

Owner: `TBD`

Responsibilities:
- `.dat` byte-stream loader；
- entropy / local entropy / byte frequency / printable ratio / zero ratio；
- n-gram / repeated prefix 等候选模式；
- packet-boundary candidate scoring；
- ground-truth boundary 指标。

Primary paths:
- `src/course_project/io/`
- `src/course_project/features/`
- `src/course_project/boundary/`

### WP2 — Protocol Structure Inference

Owner: `TBD`

Responsibilities:
- message clustering；
- sequence/message alignment；
- stable/variable regions；
- Netzob adapter；
- BinaryInferno baseline/adapter；
- field candidate normalization。

Primary path:
- `src/course_project/inference/`

### WP3 — LLM Semantic Reasoning & Evidence Verification

Owner: `TBD`

Responsibilities:
- 定义 LLM 输入 evidence schema；
- 强制结构化 hypothesis 输出；
- length/sequence/timestamp/enum/checksum 等验证器；
- ACCEPT / REJECT / UNSURE 状态；
- `LLM only` 与 `LLM + verifier` 对照实验。

Primary paths:
- `src/course_project/llm/`
- `src/course_project/verification/`

### WP4 — Traffic Behavior / ML

Owner: `TBD`

Responsibilities:
- packet/flow 特征；
- direction / timing / burst / up-down ratio；
- NFStream adapter；
- QUERY/DOWNLOAD/UPLOAD/HEARTBEAT/STREAM 数据生成和分类；
- RandomForest baseline；
- 可选高级模型评测。

Primary path:
- `src/course_project/behavior/`

### WP5 — Export / QA / Demo

Owner: `TBD`

Responsibilities:
- internal JSON schema；
- Kaitai `.ksy` export；
- parser regeneration/validation；
- Dataset A/B/C 生成和 ground truth 管理；
- end-to-end regression test；
- 演示脚本、截图、测试分析报告支撑材料。

Primary paths:
- `src/course_project/exporters/`
- `tests/`
- `examples/`
- `data/`

## 3. Collaboration Boundaries

为了减少多人同时修改同一文件：

- 每个 WP 默认只改自己的 primary paths；
- `models.py`、`docs/architecture.md`、主 pipeline 属于共享区，由 WP0 管理；
- 如果某 WP 需要共享接口变化，先开 Issue，写明 `old contract -> new contract`；
- 任何第三方工具适配都放 adapter 内，不把第三方类型扩散给其他模块；
- 每个成员至少维护一个可独立运行/测试的最小入口。

## 4. GitHub Workflow

每个工作包至少建立一个 GitHub Issue：

```text
[WP1] Implement binary feature analyzer and boundary detector
[WP2] Integrate message alignment and field inference baseline
...
```

每个 Issue 推荐拆成 1-3 个 PR，避免一个 PR 混入大量无关修改。

PR description 必须包含：
- Owner；
- linked Issue；
- modified modules；
- interface changes；
- how to test；
- evidence/result；
- remaining limitations。

## 5. Daily Integration Rule

课程周期短时，建议每天至少一次把已经 review 的模块合回 `main`，并跑一次最小端到端 smoke test。不要等所有成员最后一天再集中合并。

## 6. Final Workload Evidence

最终分工说明建议从 GitHub 直接整理：
- 每人的 Issues；
- 每人的 PR/commit；
- 每个模块测试；
- 实验负责人；
- 文档与演示负责人；
- 实际工作量占比调整说明。

最终提交前必须把本文件的 `Member A...F / TBD` 替换为真实成员信息。
