import { listen } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import type { AnalysisResult, ArtifactRef } from "./analysisContracts";

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

export interface InputMetadata {
  inputRef: string;
  kind: "dat" | "bin" | "pcap" | "pcapng" | "unknown";
  sizeBytes: number;
  sha256: string;
  sourceName: string;
  directionAvailable: boolean;
  timestampAvailable: boolean;
}

export interface RangeData {
  inputRef: string;
  offset: number;
  requestedLength: number;
  actualLength: number;
  encoding: "base64";
  bytes: string;
  eof: boolean;
}

export interface RestoredArtifactPreview {
  artifactId: string;
  format: ArtifactRef["format"];
  totalBytes: number;
  previewBytes: number;
  eof: boolean;
  bytes: number[];
  text?: string;
}

const EVENT_NAME = "task-update";
const hasTauriRuntime = () => "__TAURI_INTERNALS__" in window;
const browserTimers = new Map<string, number[]>();

function dispatchBrowserUpdate(update: TaskUpdate) {
  window.dispatchEvent(new CustomEvent<TaskUpdate>(EVENT_NAME, { detail: update }));
}

export function isDesktopRuntime() {
  return hasTauriRuntime();
}

export async function selectInput(): Promise<InputMetadata | null> {
  if (!hasTauriRuntime()) return null;
  return invoke<InputMetadata | null>("select_input");
}

export async function readInputRange(inputRef: string, offset: number, length = 256): Promise<RangeData> {
  return invoke<RangeData>("read_range", { inputRef, offset, length });
}

export async function inspectInput(inputRef: string): Promise<InputMetadata> {
  return invoke<InputMetadata>("inspect_file", { inputRef });
}

export async function startTask(failureMode: boolean, inputRef?: string): Promise<string> {
  if (hasTauriRuntime()) {
    return invoke<string>("start_contract_spike", { failureMode, inputRef });
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

export async function getAnalysisResult(taskId: string): Promise<AnalysisResult> {
  return invoke<AnalysisResult>("get_analysis_result", { taskId });
}

export async function readRestoredArtifact(
  taskId: string,
  artifactId: string,
  length = 32 * 1024,
): Promise<RestoredArtifactPreview> {
  if (hasTauriRuntime()) {
    return invoke<RestoredArtifactPreview>("read_restored_artifact", { taskId, artifactId, length });
  }
  if (taskId !== "task-demo-001" || artifactId !== "artifact-restored-001") {
    throw new Error("Artifact previews require the Tauri desktop runtime.");
  }
  const text = JSON.stringify({
    fixture: true,
    objectType: "synthetic-contract-object",
    fields: { messageType: 3, payloadLength: 12 },
  }, null, 2) + "\n";
  const bytes = Array.from(new TextEncoder().encode(text));
  return {
    artifactId,
    format: "json",
    totalBytes: bytes.length,
    previewBytes: bytes.length,
    eof: true,
    bytes,
    text,
  };
}

export async function exportRestoredArtifact(taskId: string, artifactId: string): Promise<string | null> {
  if (hasTauriRuntime()) {
    return invoke<string | null>("export_restored_artifact", { taskId, artifactId });
  }
  const preview = await readRestoredArtifact(taskId, artifactId);
  if (!preview.eof) throw new Error("The browser preview does not contain the complete artifact.");
  const blob = new Blob([Uint8Array.from(preview.bytes)], { type: "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  const extension = preview.format === "binary" ? "bin" : preview.format;
  const fileName = `${taskId}-${artifactId}.${extension}`;
  link.href = url;
  link.download = fileName;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return fileName;
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
