import { useEffect, useMemo, useState } from "react";
import { AnalysisTabs, AnalysisViewContent } from "./AnalysisViews";
import { demoAnalysisResult } from "./fixtures/demoAnalysisResult";
import type { AnalysisViewName, ByteLocation, FindingReview, AnalysisResult } from "./analysisContracts";
import {
  cancelTask,
  getAnalysisResult,
  inspectInput,
  isDesktopRuntime,
  readInputRange,
  selectInput,
  startTask,
  subscribeToTaskUpdates,
  type InputMetadata,
  type RangeData,
  type TaskStatus,
  type TaskUpdate,
} from "./taskGateway";

const statusLabel: Record<TaskStatus, string> = {
  CREATED: "Created",
  INSPECTING: "Inspecting",
  ANALYZING: "Analyzing",
  VERIFYING: "Verifying",
  COMPLETED: "Completed",
  CANCELLED: "Cancelled",
  FAILED: "Failed",
};

const initialUpdate: TaskUpdate = {
  protocolVersion: 1,
  id: "—",
  event: "status",
  status: "CREATED",
  stage: "awaiting_task",
  progress: 0,
  message: "No analysis task is running.",
};

const RANGE_SIZE = 256;

function formatBytes(size: number) {
  if (size < 1024) return size + " B";
  if (size < 1024 * 1024) return (size / 1024).toFixed(1) + " KiB";
  return (size / (1024 * 1024)).toFixed(1) + " MiB";
}

function decodeBase64(value: string) {
  const binary = window.atob(value);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function hexByte(value: number) {
  return value.toString(16).padStart(2, "0");
}

function HexView({
  input,
  range,
  loading,
  error,
  onPrevious,
  onNext,
}: {
  input: InputMetadata | null;
  range: RangeData | null;
  loading: boolean;
  error: string | null;
  onPrevious: () => void;
  onNext: () => void;
}) {
  if (!input) {
    return (
      <section className="hex-panel">
        <div className="subheading"><h3>Hex / offset view</h3><span>read_range</span></div>
        <div className="empty-state">
          <strong>No input registered</strong>
          <p>Select a supported binary file to inspect bounded byte ranges.</p>
        </div>
      </section>
    );
  }

  const bytes = range ? decodeBase64(range.bytes) : new Uint8Array();
  const rows = Array.from({ length: Math.ceil(bytes.length / 16) }, (_, rowIndex) => {
    const start = rowIndex * 16;
    const row = bytes.slice(start, start + 16);
    const hex = Array.from(row, hexByte).join(" ").padEnd(47, " ");
    const ascii = Array.from(row, (value) => value >= 32 && value <= 126 ? String.fromCharCode(value) : ".").join("");
    return { address: (range?.offset ?? 0) + start, hex, ascii };
  });

  return (
    <section className="hex-panel">
      <div className="subheading"><h3>Hex / offset view</h3><span>base64 range</span></div>
      <div className="hex-toolbar">
        <span>offset {range?.offset ?? 0}–{(range?.offset ?? 0) + (range?.actualLength ?? 0) - 1}</span>
        <div className="range-actions">
          <button className="secondary compact" disabled={loading || !range || range.offset === 0} onClick={onPrevious}>Prev</button>
          <button className="secondary compact" disabled={loading || !range || range.eof} onClick={onNext}>Next</button>
        </div>
      </div>
      {loading && <p className="range-state">Reading range…</p>}
      {error && <p className="error range-error">{error}</p>}
      {!loading && !error && rows.length > 0 && (
        <div className="hex-table" role="table" aria-label="Hexadecimal byte range">
          <div className="hex-row hex-header" role="row"><span>Offset</span><span>Bytes</span><span>ASCII</span></div>
          {rows.map((row) => (
            <div className="hex-row" key={row.address} role="row">
              <code className="hex-address">{row.address.toString(16).padStart(8, "0")}</code>
              <code className="hex-bytes">{row.hex}</code>
              <code className="hex-ascii">{row.ascii}</code>
            </div>
          ))}
        </div>
      )}
      {!loading && !error && rows.length === 0 && <p className="range-state">The selected file has no bytes in this range.</p>}
    </section>
  );
}

export function App() {
  const [update, setUpdate] = useState<TaskUpdate>(initialUpdate);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [failureMode, setFailureMode] = useState(false);
  const [input, setInput] = useState<InputMetadata | null>(null);
  const [overview, setOverview] = useState<InputMetadata | null>(null);
  const [range, setRange] = useState<RangeData | null>(null);
  const [rangeOffset, setRangeOffset] = useState(0);
  const [loadingRange, setLoadingRange] = useState(false);
  const [inputError, setInputError] = useState<string | null>(null);
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [analysisResult, setAnalysisResult] = useState<AnalysisResult | null>(null);
  const [activeView, setActiveView] = useState<AnalysisViewName>("findings");
  const [focusedLocation, setFocusedLocation] = useState<ByteLocation | null>(null);
  const [findingReviews, setFindingReviews] = useState<Record<string, FindingReview>>({});

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void subscribeToTaskUpdates((next) => {
      if (next.id === taskId || taskId === null) setUpdate(next);
    }).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  }, [taskId]);

  useEffect(() => {
    if (!input) {
      setOverview(null);
      setOverviewError(null);
      setRange(null);
      setRangeError(null);
      return;
    }
    let active = true;
    setLoadingRange(true);
    setRangeError(null);
    void readInputRange(input.inputRef, rangeOffset, RANGE_SIZE)
      .then((next) => { if (active) setRange(next); })
      .catch((error: unknown) => {
        if (active) setRangeError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => { if (active) setLoadingRange(false); });
    return () => { active = false; };
  }, [input, rangeOffset]);

  useEffect(() => {
    if (!taskId || update.status !== "COMPLETED" || !isDesktopRuntime()) return;
    let active = true;
    setAnalysisError(null);
    void getAnalysisResult(taskId)
      .then((next) => { if (active) setAnalysisResult(next); })
      .catch((error: unknown) => {
        if (active) setAnalysisError(error instanceof Error ? error.message : String(error));
      });
    return () => { active = false; };
  }, [taskId, update.status]);

  useEffect(() => {
    if (!input) return;
    let active = true;
    setOverviewError(null);
    void inspectInput(input.inputRef)
      .then((next) => { if (active) setOverview(next); })
      .catch((error: unknown) => {
        if (active) setOverviewError(error instanceof Error ? error.message : String(error));
      });
    return () => { active = false; };
  }, [input]);

  const isRunning = taskId !== null && !["COMPLETED", "FAILED", "CANCELLED"].includes(update.status);
  const stageName = useMemo(() => update.stage.replace(/_/g, " "), [update.stage]);

  async function handleSelectInput() {
    setInputError(null);
    try {
      const selected = await selectInput();
      if (!selected) {
        if (!isDesktopRuntime()) {
          setInputError("Run the Tauri desktop app to access the controlled file picker.");
        }
        return;
      }
      setInput(selected);
      setOverview(null);
      setRangeOffset(0);
    } catch (error) {
      setInputError(error instanceof Error ? error.message : String(error));
    }
  }

  async function runSpike() {
    setAnalysisResult(null);
    setAnalysisError(null);
    setFindingReviews({});
    setUpdate({ ...initialUpdate, message: input ? "Starting Sidecar analysis." : "Starting contract spike." });
    setTaskId(await startTask(failureMode, input?.inputRef));
  }

  function loadFixture() {
    setAnalysisResult(demoAnalysisResult);
    setActiveView("findings");
    setFocusedLocation(null);
    setFindingReviews({});
  }

  function jumpToLocation(location: ByteLocation) {
    setFocusedLocation(location);
    setRangeOffset(Math.floor(location.offset / RANGE_SIZE) * RANGE_SIZE);
  }

  function updateFindingReview(findingId: string, review: FindingReview) {
    setFindingReviews((current) => ({ ...current, [findingId]: review }));
  }

  function exportReview() {
    if (!analysisResult) return;
    const payload = {
      protocolVersion: 1,
      taskId: analysisResult.taskId,
      sourceResultRef: analysisResult.resultRef,
      sourceStatus: analysisResult.status,
      reviews: analysisResult.findings.map((finding) => ({
        findingId: finding.findingId,
        sourceStatus: finding.status,
        review: findingReviews[finding.findingId] || null,
      })),
      limitations: ["Local review export contains no raw bytes and is not an accepted protocol result."],
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${analysisResult.taskId}-review.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }

  async function stopTask() {
    if (taskId) await cancelTask(taskId);
  }

  return (
    <main className="workbench">
      <header className="masthead">
        <div>
          <p className="eyebrow">Course Project / D3 Controlled Restoration</p>
          <h1>Evidence Workbench</h1>
        </div>
        <div className="protocol-badge">Protocol v{update.protocolVersion}</div>
      </header>

      <section className="layout" aria-label="Desktop analysis workbench">
        <aside className="panel task-panel">
          <div className="panel-heading"><h2>Tasks</h2><span className="count">01</span></div>
          <article className="task-card" data-status={update.status}>
            <p className="task-title">Binary inspection</p>
            <p className="task-id">{taskId ?? "Not started"}</p>
            <span className="status">{statusLabel[update.status]}</span>
          </article>

          <div className="import-block">
            <div className="subheading"><h3>Input</h3><span>controlled read</span></div>
            <button className="primary file-input" onClick={() => void handleSelectInput()}>Select .dat / .bin / .pcap</button>
            {input && (
              <dl className="metadata">
                <div><dt>File</dt><dd title={input.sourceName}>{input.sourceName}</dd></div>
                <div><dt>Kind</dt><dd>{input.kind}</dd></div>
                <div><dt>Size</dt><dd>{formatBytes(input.sizeBytes)}</dd></div>
                <div><dt>SHA-256</dt><dd title={input.sha256}>{input.sha256.slice(0, 16)}…</dd></div>
              </dl>
            )}
            {inputError && <p className="error">{inputError}</p>}
          </div>

          <div className="task-actions">
            <label className="toggle-row">
              <input checked={failureMode} onChange={(event) => setFailureMode(event.target.checked)} type="checkbox" />
              Simulate analyzer failure
            </label>
            <button className="primary" disabled={isRunning} onClick={() => void runSpike()}>Start task</button>
            <button className="secondary" disabled={!taskId || !isRunning} onClick={() => void stopTask()}>Cancel task</button>
          </div>
        </aside>

        <section className="panel analysis-panel">
          <div className="panel-heading"><h2>Analysis workspace</h2><span className="mode">D3 Workbench</span></div>
          <div className="progress-block">
            <div className="progress-labels"><span>{stageName}</span><strong>{Math.round(update.progress * 100)}%</strong></div>
            <div className="progress-track" aria-label={"Task progress " + Math.round(update.progress * 100) + " percent"}>
              <div className="progress-value" style={{ width: (update.progress * 100) + "%" }} />
            </div>
          </div>
          <dl className="contract-grid">
            <div><dt>Input</dt><dd>{input?.sourceName ?? "No file selected"}</dd></div>
            <div><dt>Transport</dt><dd>{input ? "Rust range reader / Base64 contract" : "JSON Lines event envelope"}</dd></div>
            <div><dt>Stage</dt><dd>{update.stage}</dd></div>
            <div><dt>Result</dt><dd>{update.status === "COMPLETED" ? "Result reference ready" : "Not available"}</dd></div>
          </dl>
          <section className="overview-panel">
            <div className="subheading"><h3>Overview</h3><span>deterministic scan</span></div>
            {overviewError && <p className="error">{overviewError}</p>}
            {analysisError && <p className="error">Result load failed: {analysisError}</p>}
            {!input && <p className="range-state">Select an input to calculate byte-level statistics.</p>}
            {input && overview && (
              <dl className="overview-grid">
                <div><dt>Format</dt><dd>{overview.kind}</dd></div>
                <div><dt>Size</dt><dd>{formatBytes(overview.sizeBytes)}</dd></div>
                <div><dt>SHA-256</dt><dd>{overview.sha256.slice(0, 16)}…</dd></div>
                <div><dt>Direction</dt><dd>{overview.directionAvailable ? "available" : "unavailable"}</dd></div>
                <div><dt>Timestamp</dt><dd>{overview.timestampAvailable ? "available" : "unavailable"}</dd></div>
                <div><dt>Source</dt><dd>{overview.sourceName}</dd></div>
              </dl>
            )}
          </section>
          <section className="result-panel">
            <div className="subheading">
              <div><h3>Analysis result</h3><span>{analysisResult ? (isDesktopRuntime() ? analysisResult.status + " / Sidecar result" : analysisResult.status + " / fixture preview") : update.status === "COMPLETED" ? "loading result" : "awaiting result"}</span></div>
              <div className="result-actions">
                <button className="secondary compact" onClick={loadFixture}>Load synthetic fixture</button>
                <button className="secondary compact" disabled={!analysisResult} onClick={exportReview}>Export review JSON</button>
              </div>
            </div>
            {analysisResult && <p className="review-summary">{Object.keys(findingReviews).length}/{analysisResult.findings.length} findings reviewed locally; analyzer status remains unchanged.</p>}
            <AnalysisTabs active={activeView} onChange={setActiveView} hasResult={analysisResult !== null} />
            {focusedLocation && (
              <p className="focus-note">Hex focus: {focusedLocation.inputId} @ +{focusedLocation.offset} ({focusedLocation.length} bytes)</p>
            )}
            <AnalysisViewContent
              view={activeView}
              result={analysisResult}
              onJump={jumpToLocation}
              reviews={findingReviews}
              onReviewChange={updateFindingReview}
            />
          </section>
          <HexView
            input={input}
            range={range}
            loading={loadingRange}
            error={rangeError}
            onPrevious={() => setRangeOffset(Math.max(0, rangeOffset - RANGE_SIZE))}
            onNext={() => setRangeOffset(rangeOffset + (range?.actualLength || RANGE_SIZE))}
          />
          <section className="event-log" aria-label="Latest task event">
            <p className="eyebrow">Latest event</p>
            <p>{update.message}</p>
            {update.error && <p className="error">{update.error.code}: {update.error.message}</p>}
          </section>
        </section>

        <aside className="panel agent-panel">
          <div className="panel-heading"><h2>Agent</h2><span className="mode">Evidence-linked</span></div>
          <div className="agent-copy">
            <p>{update.status === "COMPLETED" ? "The task completed. Analyzer findings will appear here with byte-offset evidence." : "No protocol claim is shown until the analyzer provides a finding and verification record."}</p>
          </div>
          <dl className="agent-facts">
            <div><dt>Finding</dt><dd>{analysisResult ? analysisResult.findings.length + " linked" : "None"}</dd></div>
            <div><dt>Evidence</dt><dd>{analysisResult ? (analysisResult.evidence?.length || 0) + " records" : input ? "Input metadata" : "None"}</dd></div>
            <div><dt>Decision</dt><dd>{analysisResult?.findings[0]?.status ?? "UNCERTAIN"}</dd></div>
            <div><dt>Local review</dt><dd>{analysisResult ? Object.keys(findingReviews).length + " reviewed" : "None"}</dd></div>
          </dl>
        </aside>
      </section>
    </main>
  );
}
