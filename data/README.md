# Data

本目录只保存**允许公开、可复现、已授权**的数据说明与极小工程测试样例。

## Teacher-provided evaluation data

课程正式 `.dat` 测试数据由老师提供。开工前不需要人工构造一个替代性的正式数据集。

默认规则：
- 老师原始 `.dat` / `.bin` 文件保存在本地工作目录；
- 继续受仓库根 `.gitignore` 的 `*.dat` / `*.bin` 规则保护；
- 除非老师明确允许再分发，否则不提交原始文件；
- 收到后可在实验记录中保存安全的 metadata，例如文件大小、SHA-256、收到日期/版本、允许使用范围和老师实际提供的 ground truth/说明。

## Repository-safe fixtures

建议结构：

```text
data/
├── fixtures/       # 极小 synthetic unit/integration fixtures（非正式 benchmark）
└── raw/            # 本地老师/原始数据；默认 gitignore，不提交
```

跨语言 JSON golden fixtures 位于 `contracts/fixtures/`，它们只稳定 API/sidecar contract，不代表协议识别效果。

禁止提交：真实凭据、API key、私人流量、未经授权抓包、老师禁止再分发的数据、测试密钥和包含隐私的还原明文。

正式实验应记录 git SHA、teacher dataset id/hash、预处理、依赖/模型版本以及可用 ground truth；没有 ground truth 的指标必须明确标记为不可评估，而不是自行生成答案。
