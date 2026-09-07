# Data

本目录只保存**可公开、可复现、已授权**的数据说明与小型测试样例。

建议结构：

```text
data/
├── generated/      # 自生成数据集与 ground-truth metadata
├── fixtures/       # 很小的单元测试 fixtures
└── raw/            # 本地原始数据；默认 gitignore，不提交
```

禁止提交：真实凭据、API key、私人流量、未经授权的抓包、包含隐私的数据。

正式实验数据应记录 generator/version/seed/schema/labels，保证可复现。
