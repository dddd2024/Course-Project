import type { ReactNode } from "react";
import type { AnalysisResult } from "./analysisContracts";

type DataRecord = Record<string, unknown>;

const decisionLabels = {
  ACCEPTED: "已验证",
  REJECTED: "已排除",
  UNCERTAIN: "待验证",
} as const;

const confidenceLabels: Record<string, string> = {
  high: "高可信",
  medium: "中等可信",
  low: "低可信",
};

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
  if (value < 1024 * 1024 * 1024) return (value / (1024 * 1024)).toFixed(2) + " MiB";
  return (value / (1024 * 1024 * 1024)).toFixed(2) + " GiB";
}

function formatScore(value: unknown): string {
  const score = asNumber(value);
  return score === null ? "—" : (score * 100).toFixed(1) + "%";
}

function formatDecimal(value: number | null, digits = 4): string {
  return value === null ? "—" : value.toFixed(digits);
}

function compactJson(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  const encoded = JSON.stringify(value, null, 2);
  return encoded ? clip(encoded, 1600) : null;
}

function professionalLimitation(value: string): string | null {
  if (/\bllm\b|model|provider|hypothes/i.test(value)) return null;
  if (value.startsWith("Generic boundary and field inference used")) return null;
  if (value.startsWith("No executable length/sequence field candidate")) {
    return "当前包流尚未形成可执行的长度或序列字段候选，字段语义仍需更多同协议样本验证。";
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
      <span>证据索引</span>
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
  const payloadEvidence = asRecord(largeProfile.payloadEvidence);
  const headerEvidence = asRecord(largeProfile.headerEvidence);
  const lengthEvidence = asRecord(largeProfile.lengthEvidence);
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
  const primaryProvider = providerMetadata[0] || {};
  const usage = asRecord(primaryProvider.usage);
  const recordedModelName = providerMetadata
    .map((item) => asText(item.responseModel) || asText(item.model))
    .find((item): item is string => item !== null);
  const displayedModelName = recordedModelName || modelName;
  const liveNetworkCall = providerMetadata.some((item) => item.networkAccess === true);
  const requestCount = asNumber(semanticMetrics.llmRequestCount) || llmEvidence.length;
  const successfulRequestCount = asNumber(semanticMetrics.llmSuccessfulRequestCount) || llmEvidence.length;
  const totalTokens = asNumber(usage.total_tokens) ?? asNumber(usage.totalTokens);
  const fieldHypothesisCount = llmEvidence.filter(
    (item) => item.sourceComponent !== "track-c-llm-file-analysis",
  ).length;
  const fullFileAnalysisProduced = llmEvidence.some(
    (item) => item.sourceComponent === "track-c-llm-file-analysis",
  );

  const fullSize = asNumber(metrics.inputSizeBytes);
  const fullFileBytesScanned = asNumber(metrics.fullFileBytesScanned)
    ?? asNumber(largeProfile.bytesScanned);
  const fullFileCoverageRatio = asNumber(metrics.fullFileCoverageRatio)
    ?? asNumber(largeProfile.coverageRatio);
  const chunkCount = asNumber(largeProfile.chunkCount)
    ?? asNumber(semanticMetrics.llmFullFileChunkCount);
  const chunksIncluded = asNumber(semanticMetrics.llmFullFileChunkCountIncluded);
  const chunkSize = asNumber(largeProfile.chunkSizeBytes);
  const recordCount = asNumber(largeProfile.recordCount);
  const markerCount = asNumber(largeProfile.markerOccurrenceCount);
  const candidateMarkerCount = asNumber(largeProfile.candidateMarkerCount);
  const markerHex = asText(largeProfile.markerHex);
  const headerBytes = asNumber(largeProfile.inferredHeaderBytes);
  const entropy = asNumber(payloadEvidence.entropyBitsPerByte);
  const zlibRatio = asNumber(payloadEvidence.zlibRatio);
  const plaintextSignatures = asNumber(payloadEvidence.obviousPlaintextSignatureCount);
  const payloadSampleBytes = asNumber(payloadEvidence.sampledPayloadBytes);
  const counterUniqueRatio = asNumber(headerEvidence.counterUniqueRatio);
  const headerSampleCount = asNumber(headerEvidence.sampleCount);
  const evaluatedRecordCount = asNumber(lengthEvidence.evaluatedRecordCount);
  const ethernetRangeRatio = asNumber(lengthEvidence.ethernetRangeRatio);
  const ethernetExactCount = asNumber(lengthEvidence.ethernetExactCount);
  const profileSha = asText(largeProfile.sha256);
  const hasLargeProfile = Object.keys(largeProfile).length > 0;

  const profileConclusions = Array.isArray(largeProfile.conclusions)
    ? largeProfile.conclusions
      .map((item) => {
        const entry = asRecord(item);
        const claim = asText(entry.claim);
        return claim ? {
          claim,
          basis: textList(entry.basis),
          confidence: asText(entry.confidence),
        } : null;
      })
      .filter((item): item is { claim: string; basis: string[]; confidence: string | null } => item !== null)
    : [];
  const commonLengths = Array.isArray(largeProfile.commonRecordLengths)
    ? largeProfile.commonRecordLengths.slice(0, 5).map((item) => {
      const entry = asRecord(item);
      const length = asNumber(entry.length);
      const count = asNumber(entry.count);
      return length !== null && count !== null ? length + " B × " + count : null;
    }).filter((item): item is string => item !== null)
    : [];
  const limitations = (result.limitations || [])
    .map(professionalLimitation)
    .filter((item): item is string => item !== null);
  const orderedFindings = [...result.findings].sort((left, right) => {
    const leftModel = left.scores?.model === undefined ? 0 : 1;
    const rightModel = right.scores?.model === undefined ? 0 : 1;
    return rightModel - leftModel;
  });

  const inputFacts = [
    ["包流总量", formatBytes(fullSize)],
    ["流式分析", formatBytes(fullFileBytesScanned)],
    ["覆盖率", formatScore(fullFileCoverageRatio)],
    ["分析分段", chunkCount === null ? "—" : chunkCount + (chunkSize ? " × " + formatBytes(chunkSize) : " 段")],
    ["候选记录", recordCount === null ? "—" : String(recordCount)],
    ["重复标志", markerCount === null ? "—" : String(markerCount)],
    ["负载熵", entropy === null ? "—" : entropy.toFixed(4) + " bit/B"],
    ["压缩后比例", formatScore(zlibRatio)],
  ];

  const structuralMethods = hasLargeProfile ? [
    {
      index: "A",
      title: "记录边界",
      text: markerHex && markerCount !== null && recordCount !== null
        ? `从 ${candidateMarkerCount ?? "多组"} 个候选中定位重复标志 ${markerHex}，全流出现 ${markerCount} 次，据此切分出 ${recordCount} 条候选记录。`
        : "在完整包流中搜索重复字节标志，并以相邻标志间距建立候选记录边界。",
    },
    {
      index: "B",
      title: "封装头部",
      text: headerBytes !== null
        ? `候选封装头长度为 ${headerBytes} 字节；${headerSampleCount ?? "多组"} 个头部样本中，4 字节候选字段唯一率为 ${formatScore(counterUniqueRatio)}。`
        : "比较记录前缀的稳定字段、变化字段及跨记录唯一性，估计明文封装头范围。",
    },
    {
      index: "C",
      title: "长度关系",
      text: evaluatedRecordCount !== null
        ? `共评估 ${evaluatedRecordCount} 条记录，${ethernetExactCount ?? 0} 条精确命中经典以太网长度，${formatScore(ethernetRangeRatio)} 落入常见帧长范围。`
        : "比较记录间距、候选头长和常见链路层帧长，检验逐包封装解释。",
    },
    {
      index: "D",
      title: "负载性质",
      text: entropy !== null && zlibRatio !== null
        ? `采样 ${formatBytes(payloadSampleBytes)} 负载：熵 ${formatDecimal(entropy, 6)} bit/Byte，zlib 比率 ${formatScore(zlibRatio)}，明显明文签名 ${plaintextSignatures ?? 0} 个。`
        : "联合熵、压缩率、明文签名和块重复率，评估加密或强压缩可能性。",
    },
  ] : [];

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
          <strong>完整包流分析与推断路径</strong>
          <small>全量覆盖、结构画像、模型研判与证据结论</small>
        </span>
        <em data-state={llmEvidence.length > 0 ? "executed" : "complete"}>
          {llmEvidence.length > 0 ? "模型研判完成" : "分析完成"}
        </em>
      </summary>
      <div className="analysis-trace-content">
        <p className="analysis-trace-note">
          以下过程基于完整包流的分段统计和可追溯证据，依次说明观察到什么、如何形成推断、还存在什么竞争解释，以及下一步如何验证。
        </p>
        <ol className="analysis-trace-list">
          <TraceStep index={scopeStep} title="完整包流覆盖" meta={formatBytes(fullSize) + " · " + (result.inputId || result.taskId)}>
            <div className="analysis-fact-grid">
              {inputFacts.map(([label, value]) => (
                <div key={label}><span>{label}</span><strong>{value}</strong></div>
              ))}
            </div>
            {hasLargeProfile && (
              <p className="analysis-callout">
                完整包流已按 {formatBytes(chunkSize)} 分段连续扫描，共处理 {chunkCount ?? "—"} 段、{formatBytes(fullFileBytesScanned)} 数据，覆盖率 {formatScore(fullFileCoverageRatio)}。
                {profileSha && " 全文件 SHA-256：" + profileSha.slice(0, 16) + "…"}
              </p>
            )}
          </TraceStep>

          <TraceStep
            index={profileStep}
            title="建立包流结构画像"
            meta={chunkCount !== null ? chunkCount + " 个流式分段" : "确定性统计"}
          >
            {structuralMethods.length > 0 && (
              <div className="analysis-method-grid">
                {structuralMethods.map((method) => (
                  <article key={method.index}>
                    <span>{method.index}</span>
                    <div><strong>{method.title}</strong><p>{method.text}</p></div>
                  </article>
                ))}
              </div>
            )}
            {commonLengths.length > 0 && (
              <p className="analysis-common-lengths"><strong>高频记录长度</strong>{commonLengths.join(" · ")}</p>
            )}
            {profileConclusions.length > 0 ? (
              <div className="analysis-structural-list">
                {profileConclusions.map((conclusion, index) => (
                  <article key={index}>
                    <div>
                      <span>{String(index + 1).padStart(2, "0")}</span>
                      <strong>{conclusion.claim}</strong>
                      {conclusion.confidence && <em>{confidenceLabels[conclusion.confidence] || conclusion.confidence}</em>}
                    </div>
                    {conclusion.basis.length > 0 && (
                      <ul>{conclusion.basis.map((basis, basisIndex) => <li key={basisIndex}>{basis}</li>)}</ul>
                    )}
                  </article>
                ))}
              </div>
            ) : structuralMethods.length === 0 ? (
              <p>系统已完成完整包流的边界、消息、对齐和字段候选提取。</p>
            ) : null}
          </TraceStep>

          {modelStep !== null && (
            <TraceStep
              index={modelStep}
              title="模型综合研判"
              meta={successfulRequestCount + "/" + requestCount + " 次请求完成"
                + (totalTokens !== null ? " · " + totalTokens + " tokens" : "")}
            >
              {chunksIncluded !== null && chunkCount !== null && (
                <p className="analysis-model-context">
                  模型上下文纳入 {chunksIncluded}/{chunkCount} 个全文件分段摘要
                  {fullFileAnalysisProduced ? "，并形成完整包流综合解释。" : "。"}
                </p>
              )}
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
                      ([key]) => key !== "analysisSummary" && key !== "recommendedNextSteps" && key !== "coverage",
                    ),
                  );
                  const parameterText = Object.keys(operationalParameters).length > 0
                    ? compactJson(operationalParameters)
                    : null;
                  const interpretation = asText(observation.interpretation) as string;
                  const offset = asNumber(observation.offset);
                  const size = asNumber(observation.size);
                  const isFullFile = item.sourceComponent === "track-c-llm-file-analysis";
                  const reasoningStages = [
                    { label: "直接观察", values: observations },
                    { label: "归纳推断", values: inference ? [inference] : [] },
                    { label: "竞争解释", values: alternatives },
                    { label: "剩余不确定性", values: uncertainties },
                    { label: "验证方案", values: nextSteps },
                  ].filter((stage) => stage.values.length > 0);
                  return (
                    <article className="analysis-hypothesis" key={item.evidenceId}>
                      <div className="analysis-hypothesis-heading">
                        <div><span>综合结论</span><strong>{interpretation}</strong></div>
                        <span>置信度 {formatScore(observation.modelConfidence ?? item.score)}</span>
                      </div>
                      <p className="analysis-region">
                        {isFullFile ? "分析范围：完整包流分段画像" : "候选类型 " + (asText(observation.semanticType) || item.featureFamily)}
                        {!isFullFile && offset !== null && " · 偏移 +" + offset}
                        {!isFullFile && size !== null && " · " + size + " 字节"}
                      </p>
                      {reasoningStages.length > 0 && (
                        <div className="analysis-reasoning-chain">
                          {reasoningStages.map((stage, stageIndex) => (
                            <section key={stage.label}>
                              <span>{String(stageIndex + 1).padStart(2, "0")}</span>
                              <div>
                                <strong>{stage.label}</strong>
                                {stage.values.length === 1 ? <p>{clip(stage.values[0])}</p> : (
                                  <ul>{stage.values.map((value, index) => <li key={index}>{value}</li>)}</ul>
                                )}
                              </div>
                            </section>
                          ))}
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

          <TraceStep index={findingStep} title="形成综合结论" meta={result.findings.length + " 条可追溯判断"}>
            {orderedFindings.length > 0 ? (
              <div className="analysis-conclusion-list">
                {orderedFindings.slice(0, 24).map((finding, index) => {
                  const scoreLabels = [
                    finding.scores?.model !== undefined ? "模型置信度 " + formatScore(finding.scores.model) : null,
                    finding.scores?.evidence !== undefined ? "证据支持度 " + formatScore(finding.scores.evidence) : null,
                    finding.scores?.verification !== undefined ? "验证得分 " + formatScore(finding.scores.verification) : null,
                  ].filter((value): value is string => value !== null);
                  const isModelConclusion = finding.scores?.model !== undefined;
                  const claim = finding.claim.replace(/^模型对完整文件画像的综合解释：/, "");
                  return (
                    <article className={isModelConclusion ? "primary-conclusion" : ""} key={finding.findingId}>
                      <div className="analysis-conclusion-index">
                        <span>{String(index + 1).padStart(2, "0")}</span>
                        <em>{isModelConclusion ? "模型综合研判" : "结构证据判断"}</em>
                      </div>
                      <div className="analysis-conclusion-body">
                        <div><strong>{claim}</strong><span data-status={finding.status}>{decisionLabels[finding.status]}</span></div>
                        {scoreLabels.length > 0 && <small>{scoreLabels.join(" · ")}</small>}
                        <EvidenceReferences ids={finding.evidenceIds || []} />
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              <p>当前证据不足以形成可发布的协议结论。</p>
            )}
          </TraceStep>

          {limitationStep !== null && (
            <TraceStep index={limitationStep} title="待验证边界" meta={limitations.length + " 项"}>
              <ul className="analysis-bullet-list">
                {limitations.map((item, index) => <li key={index}>{item}</li>)}
              </ul>
              <p className="analysis-next-step">建议补充同协议多会话、不同负载长度和双向交互样本，优先验证记录边界、头部字段与长度关系的跨样本稳定性。</p>
            </TraceStep>
          )}
        </ol>
        {displayedModelName && llmEvidence.length > 0 && (
          <p className="analysis-model-name">
            分析引擎：{displayedModelName}{liveNetworkCall ? " · OpenAI 兼容 HTTPS" : ""}
            {fieldHypothesisCount > 0 ? " · " + fieldHypothesisCount + " 个字段假设" : ""}
          </p>
        )}
      </div>
    </details>
  );
}
