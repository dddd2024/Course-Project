import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";

export type TaskStatus = "CREATED" | "INSPECTING" | "ANALYZING" | "VERIFYING" | "COMPLETED" | "CANCELLED" | "FAILED";

export interface TaskUpdate {
  protocolVersion: number;
  id: string;
  event: "progress" | "status";
  status: TaskStatus;
  stage: string;
  progress: number;
  message: string;
  error?: { code: string; message: string };
}

const EVENT_NAME = "task-update";
const hasTauriRuntime = () => "__TAURI_INTERNALS__" in window;
const browserTimers = new Map<string, number[]>();

function dispatchBrowserUpdate(update: TaskUpdate) {
  window.dispatchEvent(new CustomEvent<TaskUpdate>(EVENT_NAME, { detail: update }));
}

export async function startTask(failureMode: boolean): Promise<string> {
  if (hasTauriRuntime()) {
    return invoke<string>("start_contract_spike", { failureMode });
  }

  const id = `browser-${Date.now()}`;
  const stages = [
    ["INSPECTING", "inspect_file", 0.12, "Inspecting file contract"],
    ["ANALYZING", "calculate_features", 0.44, "Calculating byte-level features"],
    ["ANALYZING", "detect_boundaries", 0.72, "Scoring message boundaries"],
    ["VERIFYING", "verify_hypotheses", 0.9, "Preparing verification result"],
    ["COMPLETED", "completed", 1, "Contract spike completed"],
  ] as const;

  const timers = stages.flatMap(([status, stage, progress, message], index) => {
    if (failureMode && index > 2) return [];
    const timer = window.setTimeout(() => {
      const failed = failureMode && index === 2;
      dispatchBrowserUpdate({
        protocolVersion: 1,
        id,
        event: status === "COMPLETED" || failed ? "status" : "progress",
        status: failed ? "FAILED" : status,
        stage,
        progress,
        message: failed ? "Mock analyzer stopped unexpectedly" : message,
        error: failed ? { code: "mock_sidecar_failed", message: "Mock analyzer stopped unexpectedly" } : undefined,
      });
      if (failed || status === "COMPLETED") browserTimers.delete(id);
    }, index * 700);
    return [timer];
  });
  browserTimers.set(id, timers);

  return id;
}

export async function cancelTask(id: string): Promise<void> {
  if (hasTauriRuntime()) {
    await invoke("cancel_contract_spike", { id });
    return;
  }
  browserTimers.get(id)?.forEach((timer) => window.clearTimeout(timer));
  browserTimers.delete(id);
  dispatchBrowserUpdate({
    protocolVersion: 1,
    id,
    event: "status",
    status: "CANCELLED",
    stage: "cancelled",
    progress: 0,
    message: "Task was cancelled by the user",
  });
}

export function subscribeToTaskUpdates(onUpdate: (update: TaskUpdate) => void) {
  if (!hasTauriRuntime()) {
    const listener = (event: Event) => onUpdate((event as CustomEvent<TaskUpdate>).detail);
    window.addEventListener(EVENT_NAME, listener);
    return Promise.resolve(() => window.removeEventListener(EVENT_NAME, listener));
  }
  return listen<TaskUpdate>(EVENT_NAME, (event) => onUpdate(event.payload));
}
