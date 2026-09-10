import { useEffect, useMemo, useState } from "react";
import type {
  AnalysisFinding,
  AnalysisResult,
  AnalysisViewName,
  ArtifactRef,
  ByteLocation,
  EvidenceRecord,
  FindingReview,
} from "./analysisContracts";
import { scoreLabel } from "./analysisContracts";
import {
  exportRestoredArtifact,
  readRestoredArtifact,
  type RestoredArtifactPreview,
} from "./taskGateway";

const labels: Record<AnalysisViewName, string> = {
  findings: "结论",
  evidence: "证据",
  artifacts: "产物",
  packets: "数据包",
  alignment: "对齐",
  statistics: "统计",
  behavior: "行为",
  restoration: "还原",
};

const decisionLabels: Record<AnalysisFinding["status"], string> = {
  ACCEPTED: "已接受",
  REJECTED: "已拒绝",
  UNCERTAIN: "待确认",
};

const artifactTypes: Partial<Record<AnalysisViewName, string[]>> = {
  packets: ["packets", "messages"],
  alignment: ["alignment"],
  statistics: ["statistics"],
  behavior: ["behavior"],
  restoration: ["restored"],
};

type RestorationState = "complete" | "unavailable" | "failed" | "incomplete" | "not-required" | "unknown";

const restorationStages = [
  { key: "extractionStatus", label: "提取" },
  { key: "decryptionStatus", label: "解密" },
  { key: "decompressionStatus", label: "解压" },
  { key: "reassemblyStatus", label: "重组" },
] as const;

const restorationStateLabels: Record<RestorationState, string> = {
  complete: "完成",
  unavailable: "不可用",
  failed: "失败",
  incomplete: "不完整",
  "not-required": "无需执行",
  unknown: "未知",
};

function normalizeRestorationState(value: unknown): RestorationState {
  if (typeof value !== "string") return "unknown";
  const normalized = value.trim().toLowerCase().replace(/[\s_]+/g, "-");
  if (["complete", "completed", "success", "succeeded"].includes(normalized)) return "complete";
  if (["unavailable", "no-key", "missing-key", "unsupported"].includes(normalized)) return "unavailable";
  if (["failed", "error"].includes(normalized)) return "failed";
  if (["incomplete", "partial", "truncated"].includes(normalized)) return "incomplete";
  if (["not-required", "skipped"].includes(normalized)) return "not-required";
  return "unknown";
}

function formatArtifactBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KiB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MiB`;
}

function BinaryArtifactPreview({ preview }: { preview: RestoredArtifactPreview }) {
  const visibleBytes = preview.bytes.slice(0, 512);
  const rows = Array.from({ length: Math.ceil(visibleBytes.length / 16) }, (_, rowIndex) => {
    const offset = rowIndex * 16;
    const row = visibleBytes.slice(offset, offset + 16);
    return {
      offset,
      hex: row.map((value) => value.toString(16).padStart(2, "0")).join(" ").padEnd(47, " "),
      ascii: row.map((value) => value >= 32 && value <= 126 ? String.fromCharCode(value) : ".").join(""),
    };
  });
  return (
    <div className="restoration-hex" role="table" aria-label="还原后二进制预览">
      {rows.map((row) => (
        <div className="restoration-hex-row" role="row" key={row.offset}>
          <code>{row.offset.toString(16).padStart(8, "0")}</code>
          <code>{row.hex}</code>
          <code>{row.ascii}</code>
        </div>
      ))}
      {preview.bytes.length > visibleBytes.length && (
        <p className="artifact-note">十六进制渲染仅显示预览中的前 512 字节。</p>
      )}
    </div>
  );
}

function RestorationView({ result }: { result: AnalysisResult }) {
  const artifacts = useMemo(
    () => (result.artifacts || []).filter((artifact) => artifact.type === "restored"),
    [result.artifacts],
  );
  const [selectedId, setSelectedId] = useState(artifacts[0]?.artifactId ?? "");
  const [preview, setPreview] = useState<RestoredArtifactPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [exportMessage, setExportMessage] = useState<string | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    setSelectedId(artifacts[0]?.artifactId ?? "");
    setExportMessage(null);
    setExportError(null);
  }, [result.taskId, artifacts]);

  const selected = artifacts.find((artifact) => artifact.artifactId === selectedId) ?? artifacts[0];

  useEffect(() => {
    if (!selected) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    let active = true;
    setLoading(true);
    setPreview(null);
    setPreviewError(null);
    void readRestoredArtifact(result.taskId, selected.artifactId)
      .then((next) => { if (active) setPreview(next); })
      .catch((error: unknown) => {
        if (active) setPreviewError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [result.taskId, selected]);

  if (!selected) {
    return (
      <div className="artifact-backed">
        <p className="view-intro">只有分析器发布受控还原产物后，才会显示还原内容。</p>
        <div className="result-empty">
          <strong>没有可用的还原产物</strong>
          <p>{result.limitations?.[0] || "分析器没有生成提取、解密、解压或重组后的输出。"}</p>
        </div>
      </div>
    );
  }

  const metadata = selected.metadata || {};
  const overallState = normalizeRestorationState(metadata.restorationStatus);

  async function handleExport() {
    setExportMessage(null);
    setExportError(null);
    try {
      const destination = await exportRestoredArtifact(result.taskId, selected.artifactId);
      if (destination) setExportMessage("已导出为 " + destination);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="restoration-view">
      <p className="view-intro">预览和导出仅限当前任务登记的受控还原产物。</p>
      <div className="restoration-heading">
        <div>
          <span className="finding-id">{selected.artifactId}</span>
          <h4>{String(metadata.contentDescription || "还原输出")}</h4>
        </div>
        <span className="restoration-state" data-state={overallState}>{restorationStateLabels[overallState]}</span>
      </div>
      {artifacts.length > 1 && (
        <label className="artifact-selector">
          <span>产物</span>
          <select value={selected.artifactId} onChange={(event) => setSelectedId(event.target.value)}>
            {artifacts.map((artifact) => <option key={artifact.artifactId} value={artifact.artifactId}>{artifact.artifactId}</option>)}
          </select>
        </label>
      )}
      <div className="restoration-track" aria-label="还原阶段状态">
        {restorationStages.map((stage, index) => {
          const state = normalizeRestorationState(metadata[stage.key]);
          return (
            <div className="restoration-stage" data-state={state} key={stage.key}>
              <span className="stage-index">{String(index + 1).padStart(2, "0")}</span>
              <strong>{stage.label}</strong>
              <span>{restorationStateLabels[state]}</span>
            </div>
          );
        })}
      </div>
      <div className="restoration-preview-heading">
        <div>
          <strong>受控预览</strong>
          <span>{selected.format} / {preview ? formatArtifactBytes(preview.totalBytes) : "正在读取大小"}</span>
        </div>
        <button className="secondary compact" onClick={() => void handleExport()}>导出产物</button>
      </div>
      {loading && <p className="range-state">正在读取受限大小的产物预览…</p>}
      {previewError && <p className="error">无法预览： {previewError}</p>}
      {preview?.text !== undefined && <pre className="restoration-text-preview">{preview.text}</pre>}
      {preview && preview.text === undefined && <BinaryArtifactPreview preview={preview} />}
      {preview && !preview.eof && (
        <p className="artifact-note">当前预览显示 {formatArtifactBytes(preview.previewBytes)}，完整产物大小为 {formatArtifactBytes(preview.totalBytes)}。导出操作会复制完整产物。</p>
      )}
      {exportMessage && <p className="export-status" role="status">{exportMessage}</p>}
      {exportError && <p className="error">导出失败： {exportError}</p>}
      <p className="restoration-safety">还原内容始终保留在本地；预览有大小限制，原始产物不会写入应用日志。</p>
    </div>
  );
}

function EmptyResult() {
  return (
    <div className="result-empty">
      <strong>尚未载入分析结果</strong>
      <p>载入合成合同示例，或运行 Sidecar 分析任务。</p>
    </div>
  );
}

function StatusBadge({ status }: { status: AnalysisFinding["status"] }) {
  return <span className={"decision decision-" + status.toLowerCase()}>{decisionLabels[status]}</span>;
}

function FindingCard({
  finding,
  onJump,
  review,
  onReviewChange,
}: {
  finding: AnalysisFinding;
  onJump: (location: ByteLocation) => void;
  review?: FindingReview;
  onReviewChange: (review: FindingReview) => void;
}) {
  const setDecision = (decision: FindingReview["decision"]) => {
    onReviewChange({ decision, correction: review?.correction || finding.claim });
  };
  return (
    <article className="finding-card">
      <div className="finding-heading">
        <div><span className="finding-id">{finding.findingId}</span><StatusBadge status={finding.status} /></div>
        {finding.semanticType && <span className="finding-type">{finding.semanticType}</span>}
      </div>
      <p className="finding-claim">{finding.claim}</p>
      <div className="finding-meta">
        <span>模型 {scoreLabel(finding.scores?.model)}</span>
        <span>证据 {scoreLabel(finding.scores?.evidence)}</span>
        <span>验证 {scoreLabel(finding.scores?.verification)}</span>
        <span>{finding.evidenceIds.length} 证据 link{finding.evidenceIds.length === 1 ? "" : "s"}</span>
      </div>
      {finding.location && (
        <button className="link-button" onClick={() => onJump(finding.location as ByteLocation)}>
          查看偏移 +{finding.location.offset} ({finding.location.length} 字节)
        </button>
      )}
      <div className="finding-review">
        <div className="review-heading">
          <span>本地复核</span>
          {review && <StatusBadge status={review.decision} />}
        </div>
        <div className="review-actions" role="group" aria-label={`复核 ${finding.findingId}`}>
          {(["ACCEPTED", "REJECTED", "UNCERTAIN"] as const).map((decision) => (
            <button
              className={review?.decision === decision ? "review-button selected" : "review-button"}
              key={decisionLabels[decision]}
              onClick={() => setDecision(decision)}
              aria-pressed={review?.decision === decision}
              type="button"
            >
              {decisionLabels[decision]}
            </button>
          ))}
        </div>
        <label className="review-correction">
          <span>修正草稿（仅保存在本地，不代表已接受的协议事实）</span>
          <textarea
            value={review?.correction ?? finding.claim}
            onChange={(event) => onReviewChange({
              decision: review?.decision ?? "UNCERTAIN",
              correction: event.target.value,
            })}
            rows={2}
          />
        </label>
      </div>
    </article>
  );
}

function EvidenceCard({ evidence }: { evidence: EvidenceRecord }) {
  return (
    <article className="evidence-card">
      <div className="finding-heading">
        <span className="finding-id">{evidence.evidenceId}</span>
        {evidence.score !== undefined && <span className="evidence-score">得分 {evidence.score.toFixed(2)}</span>}
      </div>
      <p className="evidence-source">{evidence.sourceComponent} / {evidence.method}</p>
      <dl className="evidence-facts">
        <div><dt>特征族</dt><dd>{evidence.featureFamily}</dd></div>
        <div><dt>样本</dt><dd>{evidence.sampleIds?.join(", ") || "—"}</dd></div>
        <div><dt>父证据</dt><dd>{evidence.parentEvidenceIds?.join(", ") || "无"}</dd></div>
      </dl>
      {evidence.observation && <pre className="observation">{JSON.stringify(evidence.observation, null, 2)}</pre>}
    </article>
  );
}

function ArtifactMetadata({ metadata }: { metadata: Record<string, unknown> }) {
  const entries = Object.entries(metadata);
  if (entries.length === 0) return null;
  return (
    <dl className="artifact-metadata">
      {entries.map(([key, value]) => (
        <div key={key}>
          <dt>{key}</dt>
          <dd>{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function ArtifactCard({ artifact }: { artifact: ArtifactRef }) {
  return (
    <article className="artifact-card">
      <div className="finding-heading">
        <span className="finding-id">{artifact.artifactId}</span>
        <span className="finding-type">{artifact.type}</span>
      </div>
      <p className="artifact-ref">{artifact.ref}</p>
      <div className="finding-meta">
        <span>格式 {artifact.format}</span>
        {artifact.count !== undefined && <span>{artifact.count} 条记录</span>}
      </div>
      {artifact.metadata && <ArtifactMetadata metadata={artifact.metadata} />}
      <p className="artifact-note">受控结果引用；界面不会直接内联大型产物。</p>
    </article>
  );
}

function ArtifactBackedView({ view, artifacts }: { view: AnalysisViewName; artifacts: ArtifactRef[] }) {
  const acceptedTypes = artifactTypes[view] || [];
  const matches = artifacts.filter((artifact) => acceptedTypes.includes(artifact.type));
  return (
    <div className="artifact-backed">
      <p className="view-intro">此视图由受控结果产物提供数据，大型表格不会进入 Sidecar 消息。</p>
      {matches.length > 0 ? matches.map((artifact) => <ArtifactCard key={artifact.artifactId} artifact={artifact} />) : (
        <div className="result-empty"><strong>没有{labels[view]}产物</strong><p>分析器尚未为此视图返回受控产物。</p></div>
      )}
    </div>
  );
}

export function AnalysisTabs({
  active,
  onChange,
  hasResult,
}: {
  active: AnalysisViewName;
  onChange: (view: AnalysisViewName) => void;
  hasResult: boolean;
}) {
  return (
    <nav className="analysis-tabs" aria-label="分析结果视图">
      {(Object.keys(labels) as AnalysisViewName[]).map((view) => (
        <button className={active === view ? "tab active" : "tab"} key={view} disabled={!hasResult} onClick={() => onChange(view)}>
          {labels[view]}
        </button>
      ))}
    </nav>
  );
}

export function AnalysisViewContent({
  view,
  result,
  onJump,
  reviews,
  onReviewChange,
}: {
  view: AnalysisViewName;
  result: AnalysisResult | null;
  onJump: (location: ByteLocation) => void;
  reviews: Record<string, FindingReview>;
  onReviewChange: (findingId: string, review: FindingReview) => void;
}) {
  if (!result) return <EmptyResult />;
  if (view === "findings") {
    return (
      <div className="result-list">
        {result.findings.length > 0 ? result.findings.map((finding) => (
          <FindingCard
            key={finding.findingId}
            finding={finding}
            onJump={onJump}
            review={reviews[finding.findingId]}
            onReviewChange={(review) => onReviewChange(finding.findingId, review)}
          />
        )) : <div className="result-empty"><strong>没有结论</strong><p>当前结果不包含协议结论。</p></div>}
      </div>
    );
  }
  if (view === "evidence") {
    const evidence = result.evidence || [];
    return <div className="result-list">{evidence.length > 0 ? evidence.map((item) => <EvidenceCard key={item.evidenceId} evidence={item} />) : <div className="result-empty"><strong>没有证据记录</strong><p>分析器发布来源信息后，证据会显示在这里。</p></div>}</div>;
  }
  if (view === "artifacts") {
    const artifacts = result.artifacts || [];
    return <div className="result-list">{artifacts.length > 0 ? artifacts.map((artifact) => <ArtifactCard key={artifact.artifactId} artifact={artifact} />) : <div className="result-empty"><strong>没有产物</strong><p>当前结果不包含大型视图引用。</p></div>}</div>;
  }
  if (view === "restoration") return <RestorationView result={result} />;
  return <ArtifactBackedView view={view} artifacts={result.artifacts || []} />;
}

