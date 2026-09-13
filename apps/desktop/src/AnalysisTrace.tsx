import type { ReactNode } from "react";
import type { AnalysisResult } from "./analysisContracts";

type DataRecord = Record<string, unknown>;

const decisionLabels = {
  ACCEPTED: "已接受",
  REJECTED: "已拒绝",
  UNCERTAIN: "待确认",
} as const;

function asRecord(value: unknown): DataRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as DataRecord
    : {};
}

function asText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function textList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim())
    .slice(0, 12);
}

function clip(value: string, limit = 900): string {
  return value.length > limit ? value.slice(0, limit) + "…" : value;
}

function formatBytes(value: number | null): string {
  if (value === null) return "—";
  if (value < 1024) return value + " B";
  if (value < 1024 * 1024) return (value / 1024).toFixed(1) + " KiB";
  if (value < 1024 * 1024 * 1024) return (value / (1024 * 1024)).toFixed(1) + " MiB";
  return (value / (1024 * 1024 * 1024)).toFixed(2) + " GiB";
}

function formatScore(value: unknown): string {
  const score = asNumber(value);
  return score === null ? "—" : (score * 100).toFixed(1) + "%";
}

function compactJson(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const encoded = JSON.stringify(value, null, 2);
  return encoded ? clip(encoded, 1600) : null;
}

function TraceStep({
  index,
  title,
  meta,
  children,
}: {
  index: number;
  title: string;
  meta?: string;
  children: ReactNode;
}) {
  return (
    <li className="analysis-trace-step">
      <span className="analysis-step-index">{String(index).padStart(2, "0")}</span>
      <div className="analysis-step-body">
        <div className="analysis-step-heading">
          <strong>{title}</strong>
          {meta && <span>{meta}</span>}
        </div>
        {children}
      </div>
    </li>
  );
}

function EvidenceReferences({ ids }: { ids: string[] }) {
  if (ids.length === 0) return null;
  return (
    <div className="analysis-evidence-links">
      <span>依据</span>
      {ids.slice(0, 8).map((id) => <code key={id}>{id}</code>)}
      {ids.length > 8 && <em>另有 {ids.length - 8} 条</em>}
    </div>
  );
}

export function AnalysisTrace({
  result,
  llmEnabled,
  modelName,
}: {
  result: AnalysisResult;
  llmEnabled: boolean;
  modelName?: string;
}) {
  const metrics = asRecord(result.metrics);
  const semanticMetrics = asRecord(metrics.semanticMetrics);
  const largeProfile = asRecord(metrics.largeRawProfile);
  const evidence = result.evidence || [];
  const llmEvidence = evidence.filter(
    (item) => item.sourceComponent === "track-c-llm-provider"
      || item.sourceComponent === "track-c-llm-file-analysis"
      || item.sourceComponent === "llm",
  );
  const verificationEvidence = evidence.filter(
    (item) => item.sourceComponent === "track-c-executable-verifier"
      || item.sourceComponent === "verification",
  );

  const recordedLlmRequest = semanticMetrics.llmRequested;
  const llmRequested = typeof recordedLlmRequest === "boolean" ? recordedLlmRequest : llmEnabled;
  const llmExecuted = semanticMetrics.llmExecuted === true || llmEvidence.length > 0;
  const providerMetadata = Array.isArray(semanticMetrics.llmProviderMetadata)
    ? semanticMetrics.llmProviderMetadata.map(asRecord)
    : [];
  const recordedModelName = providerMetadata
    .map((item) => asText(item.model))
    .find((item): item is string => item !== null);
  const displayedModelName = recordedModelName || modelName;
  const liveNetworkCall = providerMetadata.some((item) => item.networkAccess === true);
  const requestCount = asNumber(semanticMetrics.llmRequestCount) || 0;
  const successfulRequestCount = asNumber(semanticMetrics.llmSuccessfulRequestCount) || 0;
  const hypothesisCount = asNumber(semanticMetrics.llmHypothesisCount) || llmEvidence.length;
  const fullSize = asNumber(metrics.inputSizeBytes);
  const analyzedBytes = asNumber(metrics.analyzedBytes);
  const fullFileBytesScanned = asNumber(metrics.fullFileBytesScanned)
    ?? asNumber(largeProfile.bytesScanned);
  const fullFileCoverageRatio = asNumber(metrics.fullFileCoverageRatio)
    ?? asNumber(largeProfile.coverageRatio);
  const fullFileAnalysisProduced = semanticMetrics.llmFullFileAnalysisProduced === true;
  const profileConclusions = Array.isArray(largeProfile.conclusions)
    ? largeProfile.conclusions
      .map((item) => asText(asRecord(item).claim))
      .filter((item): item is string => item !== null)
    : [];
  const llmLimitation = (result.limitations || []).find((item) => item.toLowerCase().includes("llm"));

  const modelState = llmExecuted
    ? "模型已执行"
    : llmRequested
      ? "模型未实际执行"
      : "离线分析";
  const modelStateKind = llmExecuted ? "executed" : llmRequested ? "skipped" : "offline";

  const inputFacts = [
    ["完整文件", formatBytes(fullSize)],
    ["全文件扫描", formatBytes(fullFileBytesScanned)],
    ["扫描覆盖率", formatScore(fullFileCoverageRatio)],
    ["字段推断窗口", formatBytes(analyzedBytes)],
    ["数据包候选", String(asNumber(metrics.packetCount) || 0)],
    ["消息候选", String(asNumber(metrics.messageCount) || 0)],
    ["字段候选", String(asNumber(metrics.fieldCandidateCount) || 0)],
    ["证据记录", String(evidence.length)],
  ];

  return (
    <details className="analysis-trace" open>
      <summary>
        <span>
          <strong>详细分析思路</strong>
          <small>可审计的模型假设、证据与验证过程</small>
        </span>
        <em data-state={modelStateKind}>{modelState}</em>
      </summary>
      <div className="analysis-trace-content">
        <p className="analysis-trace-note">
          此处展示模型提交的结构化分析摘要及系统验证路径，便于复核；模型内部不可验证的隐式推理不作为证据。
        </p>
        <ol className="analysis-trace-list">
          <TraceStep index={1} title="确定分析范围" meta={result.inputId || result.taskId}>
            <div className="analysis-fact-grid">
              {inputFacts.map(([label, value]) => (
                <div key={label}><span>{label}</span><strong>{value}</strong></div>
              ))}
            </div>
            {metrics.analysisTruncated === true && (
              <p className="analysis-callout">
                字段级推断读取前 {formatBytes(analyzedBytes)}；全文件画像已流式扫描 {formatBytes(fullFileBytesScanned)}，其分段摘要用于模型的整体分析。
              </p>
            )}
          </TraceStep>

          <TraceStep
            index={2}
            title="提取结构与统计特征"
            meta={profileConclusions.length > 0 ? profileConclusions.length + " 条画像判断" : "确定性扫描"}
          >
            {asText(largeProfile.summary) && <p>{asText(largeProfile.summary)}</p>}
            {profileConclusions.length > 0 ? (
              <ul className="analysis-bullet-list">
                {profileConclusions.map((claim, index) => <li key={index}>{claim}</li>)}
              </ul>
            ) : (
              <p>系统已完成边界、消息、对齐和字段候选提取；当前结果没有额外的大型文件画像结论。</p>
            )}
          </TraceStep>

          <TraceStep
            index={3}
            title="模型分析全文件画像与候选字段"
            meta={llmExecuted
              ? successfulRequestCount + "/" + requestCount + " 次请求成功 · "
                + hypothesisCount + " 个字段假设"
                + (fullFileAnalysisProduced ? " · 已生成全文件解释" : "")
              : modelState}
          >
            {llmEvidence.length > 0 ? (
              <div className="analysis-hypothesis-list">
                {llmEvidence.map((item) => {
                  const observation = asRecord(item.observation);
                  const parameters = asRecord(observation.parameters);
                  const analysisSummary = asRecord(parameters.analysisSummary);
                  const observations = textList(analysisSummary.observations);
                  const alternatives = textList(analysisSummary.alternatives);
                  const uncertainties = textList(analysisSummary.uncertainties);
                  const inference = asText(analysisSummary.inference);
                  const operationalParameters = Object.fromEntries(
                    Object.entries(parameters).filter(([key]) => key !== "analysisSummary"),
                  );
                  const parameterText = Object.keys(operationalParameters).length > 0
                    ? compactJson(operationalParameters)
                    : null;
                  const interpretation = asText(observation.interpretation) || "模型未提供文字解释";
                  const offset = asNumber(observation.offset);
                  const size = asNumber(observation.size);
                  return (
                    <article className="analysis-hypothesis" key={item.evidenceId}>
                      <div className="analysis-hypothesis-heading">
                        <strong>{interpretation}</strong>
                        <span>模型置信度 {formatScore(observation.modelConfidence ?? item.score)}</span>
                      </div>
                      <p className="analysis-region">
                        候选类型 {asText(observation.semanticType) || item.featureFamily}
                        {offset !== null && " · 偏移 +" + offset}
                        {size !== null && " · " + size + " 字节"}
                      </p>
                      {observations.length > 0 && (
                        <div className="analysis-rationale-group">
                          <strong>关键观察</strong>
                          <ul>{observations.map((value, index) => <li key={index}>{value}</li>)}</ul>
                        </div>
                      )}
                      {inference && (
                        <div className="analysis-rationale-group">
                          <strong>推断摘要</strong>
                          <p>{clip(inference)}</p>
                        </div>
                      )}
                      {alternatives.length > 0 && (
                        <div className="analysis-rationale-group">
                          <strong>备选解释</strong>
                          <ul>{alternatives.map((value, index) => <li key={index}>{value}</li>)}</ul>
                        </div>
                      )}
                      {uncertainties.length > 0 && (
                        <div className="analysis-rationale-group">
                          <strong>不确定因素</strong>
                          <ul>{uncertainties.map((value, index) => <li key={index}>{value}</li>)}</ul>
                        </div>
                      )}
                      {parameterText && (
                        <details className="analysis-parameters">
                          <summary>查看可执行参数</summary>
                          <pre>{parameterText}</pre>
                        </details>
                      )}
                      <EvidenceReferences ids={item.parentEvidenceIds || []} />
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className="analysis-empty-stage">
                <strong>{llmRequested ? "本次没有形成模型假设" : "本次未启用模型"}</strong>
                <p>
                  {llmRequested
                    ? llmLimitation || "模型已配置，但没有满足约束的候选字段进入模型请求。"
                    : "全部判断来自本地确定性算法。启用模型后，符合条件的字段候选会进入结构化假设流程。"}
                </p>
              </div>
            )}
          </TraceStep>

          <TraceStep
            index={4}
            title="执行确定性验证"
            meta={verificationEvidence.length + " 条验证记录"}
          >
            {verificationEvidence.length > 0 ? (
              <div className="analysis-check-list">
                {verificationEvidence.slice(0, 20).map((item) => {
                  const observation = asRecord(item.observation);
                  return (
                    <article className="analysis-check" key={item.evidenceId}>
                      <div>
                        <strong>{asText(observation.checkType) || item.method}</strong>
                        <span data-result={asText(observation.result) || asText(observation.status) || "unknown"}>
                          {asText(observation.result) || asText(observation.status) || "unknown"}
                        </span>
                      </div>
                      <p>
                        样本 {asNumber(observation.sampleCount) ?? "—"} ·
                        支持 {asNumber(observation.supportCount) ?? "—"} ·
                        违反 {asNumber(observation.violationCount) ?? "—"} ·
                        得分 {formatScore(item.score)}
                      </p>
                      <EvidenceReferences ids={item.parentEvidenceIds || []} />
                    </article>
                  );
                })}
              </div>
            ) : (
              <p>没有候选假设进入可执行验证；系统不会仅凭模型置信度把假设标记为已接受。</p>
            )}
          </TraceStep>

          <TraceStep index={5} title="形成综合判断" meta={result.findings.length + " 条结论"}>
            {result.findings.length > 0 ? (
              <ul className="analysis-finding-list">
                {result.findings.slice(0, 24).map((finding) => (
                  <li key={finding.findingId}>
                    <span data-status={finding.status}>{decisionLabels[finding.status]}</span>
                    <div>
                      <strong>{finding.claim}</strong>
                      <small>
                        模型 {formatScore(finding.scores?.model)} ·
                        证据 {formatScore(finding.scores?.evidence)} ·
                        验证 {formatScore(finding.scores?.verification)}
                      </small>
                    </div>
                  </li>
                ))}
              </ul>
            ) : (
              <p>当前证据不足以形成可发布的协议结论，系统保持空结果而不补造解释。</p>
            )}
          </TraceStep>

          <TraceStep index={6} title="记录局限与下一步" meta={(result.limitations || []).length + " 项局限"}>
            {(result.limitations || []).length > 0 ? (
              <ul className="analysis-bullet-list">
                {(result.limitations || []).map((item, index) => <li key={index}>{item}</li>)}
              </ul>
            ) : (
              <p>当前分析器没有报告额外局限。仍建议结合更多同协议样本复核字段含义。</p>
            )}
            <p className="analysis-next-step">
              {llmExecuted
                ? "建议优先复核被模型引用的字节范围、父证据和验证失败项。"
                : "如需真正的模型语义分析，请确认存在字段候选并检查“模型已执行”标记；仅配置接口不代表本次已调用模型。"}
            </p>
          </TraceStep>
        </ol>
        {displayedModelName && llmRequested && (
          <p className="analysis-model-name">本次分析模型：{displayedModelName}</p>
        )}
        {llmExecuted && (
          <p className="analysis-model-name">
            接口调用：{liveNetworkCall ? "已完成 OpenAI 兼容 HTTPS 请求" : "Provider 已执行（无网络或未记录网络元数据）"}
          </p>
        )}
      </div>
    </details>
  );
}
