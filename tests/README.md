# Tests

测试分为：

```text
tests/
├── unit/          # 模块级确定性测试
├── integration/   # 相邻模块 contract 测试
└── e2e/           # .dat -> schema -> structured output
```

正式实验指标和图表不应替代测试。测试关注“代码是否按设计工作”，实验关注“方法效果有多好”。

每个 WP 在合并前至少提供：
- 正常样例；
- 边界/异常样例；
- 一个可复现失败或不确定场景。
