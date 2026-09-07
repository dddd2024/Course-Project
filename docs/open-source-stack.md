# Open-Source Stack V1

V1 采用“成熟组件做底座 + 项目自研统一推断/验证层”的策略，避免重复实现通用能力。

> Integration authority: candidate names in this document are **not automatically approved dependencies**. Before merge, exact version/commit, upstream license, environment constraints, adapter boundary and smoke/fallback behavior must be recorded in `docs/dependency-register.md`. Vendored material additionally updates `THIRD_PARTY_NOTICES.md`.

## 1. Core Candidates

### Scapy
用途：PCAP 读取、packet payload 提取、协议层基础处理。

项目边界：只负责输入预处理，不承担未知协议语义判断。

### NFStream
用途：flow 聚合与统计特征提取，用于行为分析。

项目边界：通过 adapter 输出项目统一的 feature dict / project-native record。

### Netzob
用途：protocol reverse engineering、message format inference、alignment、结构推断 baseline。

项目边界：作为结构推断底座/对照，不把 Netzob 内部对象作为跨模块接口。

### BinaryInferno
用途：binary message field inference 的研究 baseline/reference。

项目边界：用于字段候选与实验对照，不作为整个工程框架。

### Kaitai Struct
用途：将推断出的协议 schema 转换为 `.ksy`，进一步生成 parser。

项目边界：作为 export/validation 后端。

### scikit-learn
用途：RandomForest 等行为分类 baseline；只有在老师数据/补充受控数据实际支持监督分类时启用。

## 2. Optional Research Baselines

以下项目只有在 V1 主链稳定后再接入：
- NetMamba
- YaTC
- ET-BERT
- nPrint / nPrintML

目的主要是论文/实验对照，而不是让它们成为课程演示的单点依赖。

## 3. What We Build Ourselves

以下内容属于本项目核心实现：
- `.dat` 输入规范化；
- byte/statistical feature aggregation；
- packet-boundary candidate scoring；
- 统一 message/field schema；
- LLM evidence prompt 与结构化 hypothesis；
- deterministic/executable verifier；
- provenance-aware evidence aggregation；
- 统一 orchestration；
- baseline/proposed/ablation 实验；
- demo 与数据还原闭环。

## 4. Integration Policy

每个第三方组件必须满足：
1. 在 `docs/dependency-register.md` 明确 upstream、version/commit、license 和 owner；
2. 通过 adapter 接入；
3. 依赖不可用时给出 `dependency_unavailable`，不能让整个 pipeline 无提示崩溃；
4. README/文档标明哪些结果来自第三方、哪些属于项目自研；
5. 不复制大段第三方源代码后删除 attribution；
6. 实验中作为 baseline 时记录版本、参数和数据预处理方式；
7. 如果复制/再分发第三方源代码、模型、数据或示例，更新 `THIRD_PARTY_NOTICES.md`。

## 5. Dependency Strategy

核心 Python 工程使用 Python 3.11.x 作为 canonical local line，CI 同时检查 3.10/3.11。重量级/系统相关依赖不预先塞进基础 `dependencies`：各 Track 先验证实际版本/OS/Python 约束，再通过独立 PR 锁定。

桌面端由 Track B 的首个 scaffold PR 生成 Node/Rust lockfiles，并同时增加适合当前 scaffold 的 desktop CI。不要在没有可运行 scaffold 时人为制造虚假的 lockfile。

老师提供的正式 `.dat` 测试文件不属于依赖管理；其本地版本/hash/允许使用范围按 `docs/testing-plan.md` 记录。
