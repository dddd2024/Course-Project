# Examples

这里放最终演示所需的最小可复现样例。

每个 example 建议包含：
- 输入说明；
- 预期协议结构；
- 运行命令；
- 关键输出；
- 已知限制。

不要把只在某位成员电脑上才能运行的临时路径写进示例。

## Track D synthetic baseline

两个脚本在**无任何第三方依赖、无 LLM、无网络**的情况下复现 Baseline A（纯统计启发式，见 `docs/testing-plan.md` 第 5 节）：

```bash
python examples/generate_synthetic_datasets.py --outdir synthetic-datasets
python examples/run_trackd_baseline.py synthetic-datasets/dataset-a
python examples/run_trackd_baseline.py synthetic-datasets/dataset-b
python examples/run_trackd_baseline.py synthetic-datasets/dataset-c
```

- 输入：无。生成器按固定 seed 自建 A/B/C 三组合成协议数据（schema 见脚本头部注释），ground truth 与输入分离存放，确定性可复现
- 预期协议结构：`magic(4) type(1) reserved(3) seq(1) length(2 BE = total) payload`
- 关键输出：`<dataset>/baseline-metrics.json` —— boundary precision/recall/F1、field semantic accuracy、false-hypothesis-rate；dataset-c 另有 behavior_accuracy
- 已知限制：合成数据只用于工程评测，不冒充老师数据性能；字段候选含噪音（FHR ≈ 0.5），过滤噪音是 Track C 可执行验证的工作
