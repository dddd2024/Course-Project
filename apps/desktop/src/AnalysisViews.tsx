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

const labels: Record<AnalysisViewName, string> = {
  findings: "Findings",
  evidence: "Evidence",
  artifacts: "Artifacts",
  packets: "Packets",
  alignment: "Alignment",
  statistics: "Statistics",
  behavior: "Behavior",
};

const artifactTypes: Partial<Record<AnalysisViewName, string[]>> = {
  packets: ["packets", "messages"],
  alignment: ["alignment"],
  statistics: ["statistics"],
  behavior: ["behavior"],
};

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
  return <ArtifactBackedView view={view} artifacts={result.artifacts || []} />;
}

