# Contributing

本仓库采用面向多人协作的轻量 GitHub Flow。

## 分支命名

- `feature/<topic>`：新功能
- `fix/<topic>`：修复
- `docs/<topic>`：文档
- `experiment/<topic>`：实验代码与评测
- `integration/<topic>`：跨模块集成

禁止多人长期直接在 `main` 上并行开发。

## 开发流程

1. 从最新 `main` 创建独立分支。
2. 在对应 GitHub Issue 中声明工作范围、输入输出接口和负责人。
3. 只修改当前工作包需要的文件；如果必须修改共享接口，先更新 `docs/architecture.md`。
4. 提交前运行本模块测试，并保存必要的实验结果摘要。
5. 创建 Pull Request，至少由一名非作者成员 review。
6. 跨模块接口变更必须由 Integration Owner review。

## Commit 建议

采用简化 Conventional Commits：

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `test:` 测试
- `refactor:` 重构
- `chore:` 工程维护
- `exp:` 实验

## Definition of Done

一个任务只有在以下条件全部满足后才算完成：

- 代码或文档已进入 PR；
- 对应测试通过；
- 输出可由另一名成员复现；
- 新增/修改的数据结构已写入设计文档；
- 没有提交密钥、凭据、私人流量或不应公开的数据；
- 对协议推断类结果给出 evidence/confidence，而不是只有模型自然语言结论。

## 安全与数据边界

本项目仅处理课程数据、自生成数据和明确授权的实验数据。现代加密算法在没有密钥时不承诺恢复明文；对于密文主要分析其可观察结构、长度、方向、时序和统计行为。
