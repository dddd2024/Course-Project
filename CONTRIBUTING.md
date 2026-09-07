# Contributing

本仓库采用四人 Track + task-sized branch 的轻量 GitHub Flow。AI Agent 与人工开发都必须先遵守根目录 `AGENTS.md`。

## 分支命名

优先使用：

- `track-a/<topic>`：Track A integration/contracts/sidecar/CI；
- `track-b/<topic>`：Track B desktop/Tauri/React；
- `track-c/<topic>`：Track C EvidenceGraph/LLM/verification；
- `track-d/<topic>`：Track D binary/PRE/behavior；
- `fix/<topic>`：明确缺陷修复；
- `docs/<topic>`：文档；
- `experiment/<topic>`：实验代码与评测。

禁止多人长期直接在 `main` 上并行开发，也不要为每个人建立一个长期承载所有工作的个人分支。

## 开发流程

1. 从最新 `main` 创建 task-sized branch。
2. 读取自己 Track 的 GitHub Issue、`docs/tracks/track-*.md` 和相关设计。
3. 只修改当前 Track/Issue 需要的文件。
4. 如果必须修改 shared contract，先更新 schema + golden fixture + architecture/migration 说明，再更新 producer/consumer。
5. 新增第三方依赖前更新 `docs/dependency-register.md`；复制/再分发第三方材料时同时更新 `THIRD_PARTY_NOTICES.md`。
6. 提交前运行相关测试，并保存必要的实验结果/环境版本摘要。
7. 创建 Pull Request，至少由一名非作者成员 review；共享接口由 Track A + 受影响 owner review。
8. CI 全绿后再合并。

`main` 的 GitHub branch protection/ruleset 按 `docs/repository-settings.md` 配置。

## Commit 建议

采用简化 Conventional Commits：

- `feat:` 新功能
- `fix:` 修复
- `docs:` 文档
- `test:` 测试
- `refactor:` 重构
- `chore:` 工程维护
- `exp:` 实验

## Local baseline

参见 `docs/development-environment.md`。基础 Python 检查：

```bash
python -m compileall -q src
ruff check src tests
pytest -q
```

CI/离线开发默认使用 mock LLM，不需要任何真实 API key。

## Definition of Done

一个任务只有在以下条件全部满足后才算完成：

- 代码/文档通过 PR 进入 review；
- 对应 Issue acceptance criterion 满足；
- 测试与 CI 通过；
- shared contract 兼容，或有明确 migration + fixture + integration test；
- 输出可由另一名成员复现；
- 新依赖已记录版本/license/环境/adapter/fallback；
- 没有提交密钥、凭据、私人流量、老师不允许再分发的数据或敏感还原明文；
- 协议语义推断保留 evidence / verification / uncertainty，而不是只有模型自然语言结论；
- 研究结论只声明已经实现并测量的贡献。

## 数据与安全边界

课程正式 `.dat` 由老师提供，默认保存在本地并受 `.gitignore` 保护；只有在明确允许再分发时才提交原始数据。本仓库可提交极小 synthetic contract/unit fixtures，但不得把它们冒充正式课程测试结果。

现代正确实现的加密算法在没有密钥时不承诺恢复明文；对于密文主要分析其可观察结构、长度、方向、时序、统计行为和受控环境中可验证的结构信息。
