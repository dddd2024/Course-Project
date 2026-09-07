import { useEffect, useMemo, useState } from "react";
import { cancelTask, startTask, subscribeToTaskUpdates, type TaskStatus, type TaskUpdate } from "./taskGateway";

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

export function App() {
  const [update, setUpdate] = useState<TaskUpdate>(initialUpdate);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [failureMode, setFailureMode] = useState(false);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void subscribeToTaskUpdates((next) => {
      if (next.id === taskId || taskId === null) setUpdate(next);
    }).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  }, [taskId]);

  const isRunning = taskId !== null && !["COMPLETED", "FAILED", "CANCELLED"].includes(update.status);
  const stageName = useMemo(() => update.stage.replace(/_/g, " "), [update.stage]);

  async function runSpike() {
    setUpdate({ ...initialUpdate, message: "Starting contract spike." });
    setTaskId(await startTask(failureMode));
  }

  async function stopTask() {
    if (taskId) await cancelTask(taskId);
  }

  return (
    <main className="workbench">
      <header className="masthead">
        <div>
          <p className="eyebrow">Course Project / D0 Contract Spike</p>
          <h1>Evidence Workbench</h1>
        </div>
        <div className="protocol-badge">Protocol v{update.protocolVersion}</div>
      </header>

      <section className="layout" aria-label="Desktop analysis workbench">
        <aside className="panel task-panel">
          <div className="panel-heading"><h2>Tasks</h2><span className="count">01</span></div>
          <article className="task-card" data-status={update.status}>
            <p className="task-title">Contract spike</p>
            <p className="task-id">{taskId ?? "Not started"}</p>
            <span className="status">{statusLabel[update.status]}</span>
          </article>
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
          <div className="panel-heading"><h2>Analysis workspace</h2><span className="mode">Mock analyzer</span></div>
          <div className="progress-block">
            <div className="progress-labels"><span>{stageName}</span><strong>{Math.round(update.progress * 100)}%</strong></div>
            <div className="progress-track" aria-label={`Task progress ${Math.round(update.progress * 100)} percent`}>
              <div className="progress-value" style={{ width: `${update.progress * 100}%` }} />
            </div>
          </div>
          <dl className="contract-grid">
            <div><dt>Input</dt><dd>No file selected</dd></div>
            <div><dt>Transport</dt><dd>JSON Lines event envelope</dd></div>
            <div><dt>Stage</dt><dd>{update.stage}</dd></div>
            <div><dt>Result</dt><dd>{update.status === "COMPLETED" ? "Result reference ready" : "Not available"}</dd></div>
          </dl>
          <section className="event-log" aria-label="Latest task event">
            <p className="eyebrow">Latest event</p>
            <p>{update.message}</p>
            {update.error && <p className="error">{update.error.code}: {update.error.message}</p>}
          </section>
        </section>

        <aside className="panel agent-panel">
          <div className="panel-heading"><h2>Agent</h2><span className="mode">Evidence-linked</span></div>
          <div className="agent-copy">
            <p>{update.status === "COMPLETED" ? "The contract task completed. A future analyzer result can now be rendered here with byte-offset evidence." : "The Agent panel remains evidence-first. It will show no protocol claim until the analyzer provides a finding and verification record."}</p>
          </div>
          <dl className="agent-facts">
            <div><dt>Finding</dt><dd>None</dd></div>
            <div><dt>Evidence</dt><dd>None</dd></div>
            <div><dt>Decision</dt><dd>UNCERTAIN</dd></div>
          </dl>
        </aside>
      </section>
    </main>
  );
}
