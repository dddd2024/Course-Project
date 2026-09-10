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

export type StructuredOutputMode = "json_object" | "prompt_only";

export interface LlmSessionSettings {
  baseUrl: string;
  model: string;
  apiKey: string;
  structuredOutput: StructuredOutputMode;
}

export interface LlmConfigurationStatus {
  configured: boolean;
  endpointHost?: string;
  model?: string;
  inputReselectionRequired: boolean;
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

function normalizeOpenAIEndpoint(baseUrl: string) {
  const parsed = new URL(baseUrl.trim());
  if (parsed.protocol !== "https:") throw new Error("Base URL 必须使用 HTTPS。");
  if (parsed.username || parsed.password || parsed.search || parsed.hash) {
    throw new Error("Base URL 不能包含凭据、查询参数或片段。");
  }
  let path = parsed.pathname;
  while (path.endsWith("/")) path = path.slice(0, -1);
  if (path.endsWith("/chat/completions")) {
    parsed.pathname = path;
  } else if (path.endsWith("/v1")) {
    parsed.pathname = path + "/chat/completions";
  } else if (!path) {
    parsed.pathname = "/v1/chat/completions";
  } else {
    parsed.pathname = path + "/chat/completions";
  }
  return parsed.toString();
}

export async function configureLlmSession(settings: LlmSessionSettings): Promise<LlmConfigurationStatus> {
  const endpoint = normalizeOpenAIEndpoint(settings.baseUrl);
  if (!settings.model.trim()) throw new Error("请填写模型名称。");
  if (!settings.apiKey.trim()) throw new Error("请填写 API Key。");
  if (!hasTauriRuntime()) {
    return {
      configured: true,
      endpointHost: new URL(endpoint).hostname,
      model: settings.model.trim(),
      inputReselectionRequired: false,
    };
  }
  return invoke<LlmConfigurationStatus>("configure_llm", {
    settings: {
      endpoint,
      model: settings.model.trim(),
      apiKey: settings.apiKey.trim(),
      structuredOutput: settings.structuredOutput,
    },
  });
}

export async function clearLlmSession(): Promise<LlmConfigurationStatus> {
  if (!hasTauriRuntime()) {
    return { configured: false, inputReselectionRequired: false };
  }
  return invoke<LlmConfigurationStatus>("configure_llm", { settings: null });
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

export async function startTask(failureMode: boolean, inputRef?: string, llmEnabled = false): Promise<string> {
  if (hasTauriRuntime()) {
    return invoke<string>("start_contract_spike", { failureMode, inputRef, llmEnabled });
  }

  const id = `browser-${Date.now()}`;
  const stages = [
    ["INSPECTING", "inspect_file", 0.12, "Inspecting file contract"],
    ["ANALYZING", "calculate_features", 0.44, "Calculating byte-level features"],
    ["ANALYZING", "detect_boundaries", 0.72, "Scoring message boundaries"],
    ...(llmEnabled ? [["ANALYZING", "llm", 0.82, "正在请求模型生成候选假设"]] as const : []),
    ["VERIFYING", "verify_hypotheses", 0.9, "正在验证候选假设"],
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

export async function exportReviewJson(payload: unknown, suggestedName: string): Promise<string | null> {
  if (hasTauriRuntime()) {
    return invoke<string | null>("export_review_json", { payload, suggestedName });
  }
  const blob = new Blob([JSON.stringify(payload, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = suggestedName;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
  return suggestedName;
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
