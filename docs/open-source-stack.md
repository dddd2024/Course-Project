# Open-Source Stack V1

V1 采用“成熟组件做底座 + 项目自研统一推断/验证层”的策略，避免重复实现通用能力。

## 1. Core Candidates

### Scapy
用途：PCAP 读取、packet payload 提取、协议层基础处理。

项目边界：只负责输入预处理，不承担未知协议语义判断。

### NFStream
用途：flow 聚合与统计特征提取，用于行为分析。

项目边界：通过 adapter 输出项目统一的 feature dict。

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
用途：RandomForest 等行为分类 baseline。

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
- deterministic verifier；
- confidence/evidence aggregation；
- 统一 orchestration；
- baseline/proposed/ablation 实验；
- demo 与数据还原闭环。

## 4. Integration Policy

每个第三方组件必须满足：
1. 明确 license 和版本；
2. 通过 adapter 接入；
3. 依赖不可用时给出 `dependency_unavailable`，不能让整个 pipeline 无提示崩溃；
4. README/文档标明哪些结果来自第三方、哪些属于项目自研；
5. 不复制大段第三方源代码后删除 attribution；
6. 实验中把第三方组件作为 baseline 时，记录版本、参数和数据预处理方式。

## 5. Dependency Strategy

V1 的 `pyproject.toml` 暂不锁定这些重量级依赖，因为 Netzob、NFStream、深度模型可能存在 Python/OS 兼容约束。各 WP 先在独立环境验证版本，集成后再统一形成 `requirements`/lock file。
