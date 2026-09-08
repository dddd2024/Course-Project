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
  findings: "Findings",
  evidence: "Evidence",
  artifacts: "Artifacts",
  packets: "Packets",
  alignment: "Alignment",
  statistics: "Statistics",
  behavior: "Behavior",
  restoration: "Restoration",
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
  { key: "extractionStatus", label: "Extract" },
  { key: "decryptionStatus", label: "Decrypt" },
  { key: "decompressionStatus", label: "Decompress" },
  { key: "reassemblyStatus", label: "Reassemble" },
] as const;

const restorationStateLabels: Record<RestorationState, string> = {
  complete: "Complete",
  unavailable: "Unavailable",
  failed: "Failed",
  incomplete: "Incomplete",
  "not-required": "Not required",
  unknown: "Unknown",
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
    <div className="restoration-hex" role="table" aria-label="Restored binary preview">
      {rows.map((row) => (
        <div className="restoration-hex-row" role="row" key={row.offset}>
          <code>{row.offset.toString(16).padStart(8, "0")}</code>
          <code>{row.hex}</code>
          <code>{row.ascii}</code>
        </div>
      ))}
      {preview.bytes.length > visibleBytes.length && (
        <p className="artifact-note">Hex rendering is limited to the first 512 preview bytes.</p>
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
        <p className="view-intro">Restored content appears only when the analyzer advertises a controlled restored artifact.</p>
        <div className="result-empty">
          <strong>No restored artifact advertised</strong>
          <p>{result.limitations?.[0] || "The analyzer did not produce extracted, decrypted, decompressed or reassembled output."}</p>
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
      if (destination) setExportMessage(`Exported as ${destination}`);
    } catch (error) {
      setExportError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <div className="restoration-view">
      <p className="view-intro">Preview and export are restricted to restored artifacts registered by this task.</p>
      <div className="restoration-heading">
        <div>
          <span className="finding-id">{selected.artifactId}</span>
          <h4>{String(metadata.contentDescription || "Restored output")}</h4>
        </div>
        <span className="restoration-state" data-state={overallState}>{restorationStateLabels[overallState]}</span>
      </div>
      {artifacts.length > 1 && (
        <label className="artifact-selector">
          <span>Artifact</span>
          <select value={selected.artifactId} onChange={(event) => setSelectedId(event.target.value)}>
            {artifacts.map((artifact) => <option key={artifact.artifactId} value={artifact.artifactId}>{artifact.artifactId}</option>)}
          </select>
        </label>
      )}
      <div className="restoration-track" aria-label="Restoration stage status">
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
          <strong>Controlled preview</strong>
          <span>{selected.format} / {preview ? formatArtifactBytes(preview.totalBytes) : "size pending"}</span>
        </div>
        <button className="secondary compact" onClick={() => void handleExport()}>Export artifact</button>
      </div>
      {loading && <p className="range-state">Reading the bounded artifact preview…</p>}
      {previewError && <p className="error">Preview unavailable: {previewError}</p>}
      {preview?.text !== undefined && <pre className="restoration-text-preview">{preview.text}</pre>}
      {preview && preview.text === undefined && <BinaryArtifactPreview preview={preview} />}
      {preview && !preview.eof && (
        <p className="artifact-note">Preview shows {formatArtifactBytes(preview.previewBytes)} of {formatArtifactBytes(preview.totalBytes)}. Export copies the complete artifact.</p>
      )}
      {exportMessage && <p className="export-status" role="status">{exportMessage}</p>}
      {exportError && <p className="error">Export failed: {exportError}</p>}
      <p className="restoration-safety">Restored content stays local. The preview is bounded and the original artifact is not written to application logs.</p>
    </div>
  );
}

function EmptyResult() {
  return (
    <div className="result-empty">
      <strong>No analysis result loaded</strong>
      <p>Load the synthetic contract fixture or run the sidecar analysis task.</p>
    </div>
  );
}

function StatusBadge({ status }: { status: AnalysisFinding["status"] }) {
  return <span className={"decision decision-" + status.toLowerCase()}>{status}</span>;
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
        <span>model {scoreLabel(finding.scores?.model)}</span>
        <span>evidence {scoreLabel(finding.scores?.evidence)}</span>
        <span>verification {scoreLabel(finding.scores?.verification)}</span>
        <span>{finding.evidenceIds.length} evidence link{finding.evidenceIds.length === 1 ? "" : "s"}</span>
      </div>
      {finding.location && (
        <button className="link-button" onClick={() => onJump(finding.location as ByteLocation)}>
          Inspect offset +{finding.location.offset} ({finding.location.length} bytes)
        </button>
      )}
      <div className="finding-review">
        <div className="review-heading">
          <span>Local review</span>
          {review && <StatusBadge status={review.decision} />}
        </div>
        <div className="review-actions" role="group" aria-label={`Review ${finding.findingId}`}>
          {(["ACCEPTED", "REJECTED", "UNCERTAIN"] as const).map((decision) => (
            <button
              className={review?.decision === decision ? "review-button selected" : "review-button"}
              key={decision}
              onClick={() => setDecision(decision)}
              aria-pressed={review?.decision === decision}
              type="button"
            >
              {decision}
            </button>
          ))}
        </div>
        <label className="review-correction">
          <span>Correction draft (local, not an accepted protocol fact)</span>
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
        {evidence.score !== undefined && <span className="evidence-score">score {evidence.score.toFixed(2)}</span>}
      </div>
      <p className="evidence-source">{evidence.sourceComponent} / {evidence.method}</p>
      <dl className="evidence-facts">
        <div><dt>Feature family</dt><dd>{evidence.featureFamily}</dd></div>
        <div><dt>Samples</dt><dd>{evidence.sampleIds?.join(", ") || "—"}</dd></div>
        <div><dt>Parents</dt><dd>{evidence.parentEvidenceIds?.join(", ") || "none"}</dd></div>
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
        <span>format {artifact.format}</span>
        {artifact.count !== undefined && <span>{artifact.count} records</span>}
      </div>
      {artifact.metadata && <ArtifactMetadata metadata={artifact.metadata} />}
      <p className="artifact-note">Controlled result reference; the UI does not inline the artifact.</p>
    </article>
  );
}

function ArtifactBackedView({ view, artifacts }: { view: AnalysisViewName; artifacts: ArtifactRef[] }) {
  const acceptedTypes = artifactTypes[view] || [];
  const matches = artifacts.filter((artifact) => acceptedTypes.includes(artifact.type));
  return (
    <div className="artifact-backed">
      <p className="view-intro">This view is backed by controlled result artifacts. Large tables stay outside the sidecar message.</p>
      {matches.length > 0 ? matches.map((artifact) => <ArtifactCard key={artifact.artifactId} artifact={artifact} />) : (
        <div className="result-empty"><strong>No {labels[view].toLowerCase()} artifact advertised</strong><p>The analyzer has not returned a controlled artifact for this view.</p></div>
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
    <nav className="analysis-tabs" aria-label="Analysis result views">
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
        )) : <div className="result-empty"><strong>No findings</strong><p>The result contains no protocol claims.</p></div>}
      </div>
    );
  }
  if (view === "evidence") {
    const evidence = result.evidence || [];
    return <div className="result-list">{evidence.length > 0 ? evidence.map((item) => <EvidenceCard key={item.evidenceId} evidence={item} />) : <div className="result-empty"><strong>No evidence records</strong><p>Evidence will appear when the analyzer publishes provenance.</p></div>}</div>;
  }
  if (view === "artifacts") {
    const artifacts = result.artifacts || [];
    return <div className="result-list">{artifacts.length > 0 ? artifacts.map((artifact) => <ArtifactCard key={artifact.artifactId} artifact={artifact} />) : <div className="result-empty"><strong>No artifacts</strong><p>The result contains no large-view references.</p></div>}</div>;
  }
  if (view === "restoration") return <RestorationView result={result} />;
  return <ArtifactBackedView view={view} artifacts={result.artifacts || []} />;
}

