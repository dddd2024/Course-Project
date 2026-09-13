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

function professionalLimitation(value: string): string | null {
  if (/\bllm\b|model|provider|hypothes/i.test(value)) return null;
  if (value.startsWith("No executable length/sequence field candidate")) {
    return "当前样本未形成可执行的长度或序列字段候选，字段语义仍需更多样本验证。";
  }
  if (value.startsWith("Generic boundary and field inference used")) {
    return "字段级推断基于受控分析窗口；全文件结构画像覆盖全部字节，窗口内字段偏移仍为文件绝对偏移。";
  }
  return value;
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
  modelName,
}: {
  result: AnalysisResult;
  modelName?: string;
}) {
  const metrics = asRecord(result.metrics);
  const semanticMetrics = asRecord(metrics.semanticMetrics);
  const largeProfile = asRecord(metrics.largeRawProfile);
  const evidence = result.evidence || [];
  const llmEvidence = evidence.filter((item) => {
    const fromModel = item.sourceComponent === "track-c-llm-provider"
      || item.sourceComponent === "track-c-llm-file-analysis"
      || item.sourceComponent === "llm";
    return fromModel && asText(asRecord(item.observation).interpretation) !== null;
  });
  const verificationEvidence = evidence.filter(
    (item) => item.sourceComponent === "track-c-executable-verifier"
      || item.sourceComponent === "verification",
  );

  const providerMetadata = Array.isArray(semanticMetrics.llmProviderMetadata)
    ? semanticMetrics.llmProviderMetadata.map(asRecord)
    : [];
  const recordedModelName = providerMetadata
    .map((item) => asText(item.model))
    .find((item): item is string => item !== null);
  const displayedModelName = recordedModelName || modelName;
  const liveNetworkCall = providerMetadata.some((item) => item.networkAccess === true);
  const requestCount = asNumber(semanticMetrics.llmRequestCount) || llmEvidence.length;
  const successfulRequestCount = asNumber(semanticMetrics.llmSuccessfulRequestCount) || llmEvidence.length;
  const fieldHypothesisCount = llmEvidence.filter(
    (item) => item.sourceComponent !== "track-c-llm-file-analysis",
  ).length;
  const fullFileAnalysisProduced = llmEvidence.some(
    (item) => item.sourceComponent === "track-c-llm-file-analysis",
  );
  const fullSize = asNumber(metrics.inputSizeBytes);
  const analyzedBytes = asNumber(metrics.analyzedBytes);
  const fullFileBytesScanned = asNumber(metrics.fullFileBytesScanned)
    ?? asNumber(largeProfile.bytesScanned);
  const fullFileCoverageRatio = asNumber(metrics.fullFileCoverageRatio)
    ?? asNumber(largeProfile.coverageRatio);
  const profileConclusions = Array.isArray(largeProfile.conclusions)
    ? largeProfile.conclusions
      .map((item) => asText(asRecord(item).claim))
      .filter((item): item is string => item !== null)
    : [];
  const limitations = (result.limitations || [])
    .map(professionalLimitation)
    .filter((item): item is string => item !== null);

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
  let nextIndex = 1;
  const scopeStep = nextIndex++;
  const profileStep = nextIndex++;
  const modelStep = llmEvidence.length > 0 ? nextIndex++ : null;
  const verificationStep = verificationEvidence.length > 0 ? nextIndex++ : null;
  const findingStep = nextIndex++;
  const limitationStep = limitations.length > 0 ? nextIndex++ : null;

  return (
    <details className="analysis-trace" open>
      <summary>
        <span>
          <strong>分析依据与推断路径</strong>
          <small>扫描范围、结构证据、模型解释与验证结论</small>
        </span>
        <em data-state={llmEvidence.length > 0 ? "executed" : "complete"}>
          {llmEvidence.length > 0 ? "模型分析完成" : "分析完成"}
        </em>
      </summary>
      <div className="analysis-trace-content">
        <p className="analysis-trace-note">
          报告按证据链展示可复核的观察、推断、备选解释与不确定因素。模型解释仅在成功解析并留存证据后出现。
        </p>
        <ol className="analysis-trace-list">
          <TraceStep index={scopeStep} title="确定分析范围" meta={result.inputId || result.taskId}>
            <div className="analysis-fact-grid">
              {inputFacts.map(([label, value]) => (
                <div key={label}><span>{label}</span><strong>{value}</strong></div>
              ))}
            </div>
            {metrics.analysisTruncated === true && (
              <p className="analysis-callout">
                字段级推断读取前 {formatBytes(analyzedBytes)}；全文件画像已流式扫描 {formatBytes(fullFileBytesScanned)}，其分段摘要用于整体分析。
              </p>
            )}
          </TraceStep>

          <TraceStep
            index={profileStep}
            title="提取结构与统计特征"
            meta={profileConclusions.length > 0 ? profileConclusions.length + " 条画像判断" : "确定性扫描"}
          >
            {profileConclusions.length > 0 ? (
              <ul className="analysis-bullet-list">
                {profileConclusions.map((claim, index) => <li key={index}>{claim}</li>)}
              </ul>
            ) : (
              <p>系统已完成边界、消息、对齐和字段候选提取。</p>
            )}
          </TraceStep>

          {modelStep !== null && (
            <TraceStep
              index={modelStep}
              title="模型分析全文件画像与候选字段"
              meta={successfulRequestCount + "/" + requestCount + " 次请求完成"
                + (fullFileAnalysisProduced ? " · 全文件解释" : "")
                + (fieldHypothesisCount > 0 ? " · " + fieldHypothesisCount + " 个字段假设" : "")}
            >
              <div className="analysis-hypothesis-list">
                {llmEvidence.map((item) => {
                  const observation = asRecord(item.observation);
                  const parameters = asRecord(observation.parameters);
                  const analysisSummary = asRecord(parameters.analysisSummary);
                  const observations = textList(analysisSummary.observations);
                  const alternatives = textList(analysisSummary.alternatives);
                  const uncertainties = textList(analysisSummary.uncertainties);
                  const inference = asText(analysisSummary.inference);
                  const nextSteps = textList(parameters.recommendedNextSteps);
                  const operationalParameters = Object.fromEntries(
                    Object.entries(parameters).filter(
                      ([key]) => key !== "analysisSummary" && key !== "recommendedNextSteps",
                    ),
                  );
                  const parameterText = Object.keys(operationalParameters).length > 0
                    ? compactJson(operationalParameters)
                    : null;
                  const interpretation = asText(observation.interpretation) as string;
                  const offset = asNumber(observation.offset);
                  const size = asNumber(observation.size);
                  const isFullFile = item.sourceComponent === "track-c-llm-file-analysis";
                  return (
                    <article className="analysis-hypothesis" key={item.evidenceId}>
                      <div className="analysis-hypothesis-heading">
                        <strong>{interpretation}</strong>
                        <span>置信度 {formatScore(observation.modelConfidence ?? item.score)}</span>
                      </div>
                      <p className="analysis-region">
                        {isFullFile ? "分析范围：完整文件分段画像" : "候选类型 " + (asText(observation.semanticType) || item.featureFamily)}
                        {!isFullFile && offset !== null && " · 偏移 +" + offset}
                        {!isFullFile && size !== null && " · " + size + " 字节"}
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
                      {nextSteps.length > 0 && (
                        <div className="analysis-rationale-group">
                          <strong>建议验证</strong>
                          <ul>{nextSteps.map((value, index) => <li key={index}>{value}</li>)}</ul>
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
            </TraceStep>
          )}

          {verificationStep !== null && (
            <TraceStep index={verificationStep} title="执行确定性验证" meta={verificationEvidence.length + " 条验证记录"}>
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
                        样本 {asNumber(observation.sampleCount) ?? "—"} · 支持 {asNumber(observation.supportCount) ?? "—"} · 违反 {asNumber(observation.violationCount) ?? "—"} · 得分 {formatScore(item.score)}
                      </p>
                      <EvidenceReferences ids={item.parentEvidenceIds || []} />
                    </article>
                  );
                })}
              </div>
            </TraceStep>
          )}

          <TraceStep index={findingStep} title="形成综合判断" meta={result.findings.length + " 条结论"}>
            {result.findings.length > 0 ? (
              <ul className="analysis-finding-list">
                {result.findings.slice(0, 24).map((finding) => {
                  const scoreLabels = [
                    finding.scores?.model !== undefined ? "模型 " + formatScore(finding.scores.model) : null,
                    finding.scores?.evidence !== undefined ? "证据 " + formatScore(finding.scores.evidence) : null,
                    finding.scores?.verification !== undefined ? "验证 " + formatScore(finding.scores.verification) : null,
                  ].filter((value): value is string => value !== null);
                  return (
                    <li key={finding.findingId}>
                      <span data-status={finding.status}>{decisionLabels[finding.status]}</span>
                      <div>
                        <strong>{finding.claim}</strong>
                        {scoreLabels.length > 0 && <small>{scoreLabels.join(" · ")}</small>}
                      </div>
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p>当前证据不足以形成可发布的协议结论。</p>
            )}
          </TraceStep>

          {limitationStep !== null && (
            <TraceStep index={limitationStep} title="记录局限与下一步" meta={limitations.length + " 项局限"}>
              <ul className="analysis-bullet-list">
                {limitations.map((item, index) => <li key={index}>{item}</li>)}
              </ul>
              <p className="analysis-next-step">建议结合更多同协议样本，复核候选边界、长度关系与跨包稳定性。</p>
            </TraceStep>
          )}
        </ol>
        {displayedModelName && llmEvidence.length > 0 && (
          <p className="analysis-model-name">
            分析引擎：{displayedModelName}{liveNetworkCall ? " · OpenAI 兼容 HTTPS" : ""}
          </p>
        )}
      </div>
    </details>
  );
}
