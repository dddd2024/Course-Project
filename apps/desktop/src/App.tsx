import { useEffect, useMemo, useState } from "react";
import { AnalysisTabs, AnalysisViewContent } from "./AnalysisViews";
import { demoAnalysisResult } from "./fixtures/demoAnalysisResult";
import type { AnalysisViewName, ByteLocation, FindingReview, AnalysisResult } from "./analysisContracts";
import {
  cancelTask,
  clearLlmSession,
  configureLlmSession,
  exportReviewJson,
  getAnalysisResult,
  inspectInput,
  isDesktopRuntime,
  readInputRange,
  selectInput,
  startTask,
  subscribeToTaskUpdates,
  type InputMetadata,
  type LlmConfigurationStatus,
  type LlmSessionSettings,
  type RangeData,
  type StructuredOutputMode,
  type TaskStatus,
  type TaskUpdate,
} from "./taskGateway";

const statusLabel: Record<TaskStatus, string> = {
  CREATED: "等待开始",
  INSPECTING: "正在检查",
  ANALYZING: "正在分析",
  VERIFYING: "正在验证",
  COMPLETED: "分析完成",
  CANCELLED: "已取消",
  FAILED: "分析失败",
};

const stageLabel: Record<string, string> = {
  awaiting_task: "等待任务",
  inspect_file: "检查文件",
  calculate_features: "提取特征",
  detect_boundaries: "识别边界",
  analysis: "分析数据",
  llm: "模型推理",
  verify_hypotheses: "验证假设",
  completed: "已完成",
  cancelled: "已取消",
  start_failed: "启动失败",
};

const initialUpdate: TaskUpdate = {
  protocolVersion: 1,
  id: "—",
  event: "status",
  status: "CREATED",
  stage: "awaiting_task",
  progress: 0,
  message: "尚未启动分析任务。",
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

function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 32 32">
        <path d="M16 3.5c2.3 4.5 2.3 8.2 0 11.2-2.3-3-2.3-6.7 0-11.2Z" />
        <path d="M28.5 16c-4.5 2.3-8.2 2.3-11.2 0 3-2.3 6.7-2.3 11.2 0Z" />
        <path d="M16 28.5c-2.3-4.5-2.3-8.2 0-11.2 2.3 3 2.3 6.7 0 11.2Z" />
        <path d="M3.5 16c4.5-2.3 8.2-2.3 11.2 0-3 2.3-6.7 2.3-11.2 0Z" />
      </svg>
    </span>
  );
}

function SettingsIcon() {
  return (
    <svg className="button-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.6v-.2h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z" />
    </svg>
  );
}

function ModelSettingsDrawer({
  open,
  busy,
  configured,
  currentHost,
  currentModel,
  onClose,
  onSave,
  onClear,
}: {
  open: boolean;
  busy: boolean;
  configured: boolean;
  currentHost?: string;
  currentModel?: string;
  onClose: () => void;
  onSave: (settings: LlmSessionSettings) => Promise<void>;
  onClear: () => Promise<void>;
}) {
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState(currentModel || "");
  const [apiKey, setApiKey] = useState("");
  const [structuredOutput, setStructuredOutput] = useState<StructuredOutputMode>("json_object");
  const [showKey, setShowKey] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setModel(currentModel || "");
      setApiKey("");
      setFormError(null);
      setShowKey(false);
    }
  }, [open, currentModel]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setFormError(null);
    try {
      await onSave({ baseUrl, model, apiKey, structuredOutput });
      setApiKey("");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  async function clear() {
    setSaving(true);
    setFormError(null);
    try {
      await onClear();
      setApiKey("");
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    } finally {
      setSaving(false);
    }
  }

  if (!open) return null;

  return (
    <div className="drawer-layer" role="presentation">
      <button className="drawer-backdrop" aria-label="关闭模型设置" onClick={onClose} />
      <aside className="settings-drawer" aria-label="模型设置">
        <div className="drawer-heading">
          <div>
            <p className="section-kicker">当前会话</p>
            <h2>模型设置</h2>
          </div>
          <button className="text-button" onClick={onClose}>关闭</button>
        </div>

        <div className="privacy-note">
          <strong>密钥仅保存在内存中</strong>
          <p>API Key 不会写入项目、分析结果或应用日志。关闭应用后配置自动清除。</p>
        </div>

        {configured && (
          <div className="configured-summary">
            <span className="connection-dot" />
            <div>
              <strong>已连接到本次会话</strong>
              <p>{currentHost} · {currentModel}</p>
            </div>
          </div>
        )}

        <form className="settings-form" onSubmit={(event) => void submit(event)}>
          <label>
            <span>Base URL</span>
            <input
              autoComplete="url"
              inputMode="url"
              placeholder="例如：https://provider.example/v1"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
            />
            <small>可填写服务根地址或完整的 /chat/completions 地址。</small>
          </label>

          <label>
            <span>模型名称</span>
            <input
              autoComplete="off"
              placeholder="例如：你的模型部署名称"
              value={model}
              onChange={(event) => setModel(event.target.value)}
            />
          </label>

          <label>
            <span>API Key</span>
            <div className="secret-input">
              <input
                autoComplete="off"
                placeholder="仅用于本次桌面会话"
                type={showKey ? "text" : "password"}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
              <button type="button" onClick={() => setShowKey((value) => !value)}>
                {showKey ? "隐藏" : "显示"}
              </button>
            </div>
          </label>

          <label>
            <span>结构化输出</span>
            <select value={structuredOutput} onChange={(event) => setStructuredOutput(event.target.value as StructuredOutputMode)}>
              <option value="json_object">JSON 对象模式</option>
              <option value="prompt_only">仅使用提示词约束</option>
            </select>
            <small>部分兼容服务不支持 response_format，可切换为仅提示词约束。</small>
          </label>

          {!isDesktopRuntime() && (
            <p className="browser-note">当前是浏览器预览，只验证界面。真实模型调用需要在 Tauri 桌面端运行。</p>
          )}
          {formError && <p className="error form-error">{formError}</p>}

          <button className="primary wide" disabled={saving || busy} type="submit">
            {saving ? "正在保存…" : "保存到本次会话"}
          </button>
          {configured && (
            <button className="secondary wide" disabled={saving || busy} type="button" onClick={() => void clear()}>
              停用并清除配置
            </button>
          )}
        </form>
      </aside>
    </div>
  );
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
      <section className="content-card hex-panel">
        <div className="section-heading"><h3>十六进制视图</h3><span>按需读取</span></div>
        <div className="empty-state">
          <strong>还没有输入文件</strong>
          <p>选择受支持的二进制文件后，可在这里检查受控字节范围。</p>
        </div>
      </section>
    );
  }

  const bytes = range ? decodeBase64(range.bytes) : new Uint8Array();
  const rows = Array.from({ length: Math.ceil(bytes.length / 16) }, (_, rowIndex) => {
    const start = rowIndex * 16;
    const row = bytes.slice(start, start + 16);
    return {
      address: (range?.offset ?? 0) + start,
      hex: Array.from(row, hexByte).join(" ").padEnd(47, " "),
      ascii: Array.from(row, (value) => value >= 32 && value <= 126 ? String.fromCharCode(value) : ".").join(""),
    };
  });

  return (
    <section className="content-card hex-panel">
      <div className="section-heading">
        <div><h3>十六进制视图</h3><span>偏移 {range?.offset ?? 0} · 最多读取 {RANGE_SIZE} 字节</span></div>
        <div className="range-actions">
          <button className="quiet-button" disabled={loading || !range || range.offset === 0} onClick={onPrevious}>上一段</button>
          <button className="quiet-button" disabled={loading || !range || range.eof} onClick={onNext}>下一段</button>
        </div>
      </div>
      {loading && <p className="range-state">正在读取字节范围…</p>}
      {error && <p className="error">{error}</p>}
      {!loading && !error && rows.length > 0 && (
        <div className="hex-table" role="table" aria-label="十六进制字节范围">
          <div className="hex-row hex-header" role="row"><span>偏移</span><span>字节</span><span>ASCII</span></div>
          {rows.map((row) => (
            <div className="hex-row" key={row.address} role="row">
              <code className="hex-address">{row.address.toString(16).padStart(8, "0")}</code>
              <code className="hex-bytes">{row.hex}</code>
              <code className="hex-ascii">{row.ascii}</code>
            </div>
          ))}
        </div>
      )}
      {!loading && !error && rows.length === 0 && <p className="range-state">当前范围没有可显示的字节。</p>}
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
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [llmStatus, setLlmStatus] = useState<LlmConfigurationStatus>({ configured: false, inputReselectionRequired: false });
  const [llmEnabled, setLlmEnabled] = useState(false);
  const [sessionNotice, setSessionNotice] = useState<string | null>(null);
  const [reviewExporting, setReviewExporting] = useState(false);
  const [reviewExportError, setReviewExportError] = useState<string | null>(null);

  useEffect(() => {
    let unlisten: (() => void) | undefined;
    void subscribeToTaskUpdates(setUpdate).then((dispose) => { unlisten = dispose; });
    return () => unlisten?.();
  }, []);

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
  const stageName = useMemo(() => stageLabel[update.stage] || update.stage.replace(/_/g, " "), [update.stage]);
  const assistantText = useMemo(() => {
    if (update.status === "FAILED") return "分析未完成。请查看错误信息，修正配置或输入后重新运行。";
    if (update.status === "COMPLETED" && analysisResult) {
      return "分析已完成，共生成 " + analysisResult.findings.length + " 条结论和 " + (analysisResult.evidence?.length || 0) + " 条证据记录。模型输出仍需经过确定性验证后才会成为已接受结论。";
    }
    if (update.status === "COMPLETED") return "分析已完成，正在读取结构化结果。";
    if (isRunning) return "正在执行“" + stageName + "”。界面会保留每条结论对应的证据与字节位置。";
    if (input) return "文件已登记。你可以使用离线分析，也可以启用已配置的模型来辅助生成协议语义假设。";
    return "选择一个 .dat、.bin、.pcap 或 .pcapng 文件开始。原始字节只通过受控范围读取。";
  }, [analysisResult, input, isRunning, stageName, update.status]);

  async function handleSelectInput() {
    setInputError(null);
    setSessionNotice(null);
    try {
      const selected = await selectInput();
      if (!selected) {
        if (!isDesktopRuntime()) setInputError("文件选择需要在 Tauri 桌面端中使用。");
        return;
      }
      setInput(selected);
      setOverview(null);
      setRangeOffset(0);
    } catch (error) {
      setInputError(error instanceof Error ? error.message : String(error));
    }
  }

  async function handleConfigureLlm(settings: LlmSessionSettings) {
    const next = await configureLlmSession(settings);
    setLlmStatus(next);
    setLlmEnabled(next.configured);
    if (next.inputReselectionRequired) {
      setInput(null);
      setOverview(null);
      setRange(null);
      setRangeOffset(0);
      setSessionNotice("模型配置已更新。Sidecar 已安全重启，请重新选择输入文件。");
    } else {
      setSessionNotice("模型配置已应用到本次会话。");
    }
    setSettingsOpen(false);
  }

  async function handleClearLlm() {
    const next = await clearLlmSession();
    setLlmStatus(next);
    setLlmEnabled(false);
    if (next.inputReselectionRequired) {
      setInput(null);
      setOverview(null);
      setRange(null);
      setRangeOffset(0);
      setSessionNotice("模型配置已清除。Sidecar 已重启，请重新选择输入文件。");
    } else {
      setSessionNotice("本次会话的模型配置已清除。");
    }
    setSettingsOpen(false);
  }

  async function runAnalysis() {
    setAnalysisResult(null);
    setAnalysisError(null);
    setFindingReviews({});
    setSessionNotice(null);
    setReviewExportError(null);
    setUpdate({ ...initialUpdate, message: "正在启动分析任务。" });
    try {
      setTaskId(await startTask(failureMode, input?.inputRef, llmEnabled));
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      setAnalysisError(message);
      setUpdate({
        ...initialUpdate,
        status: "FAILED",
        stage: "start_failed",
        message: "无法启动分析任务。",
        error: { code: "task_start_failed", message },
      });
    }
  }

  function loadFixture() {
    setAnalysisResult(demoAnalysisResult);
    setActiveView("findings");
    setFocusedLocation(null);
    setFindingReviews({});
    setReviewExportError(null);
  }

  function jumpToLocation(location: ByteLocation) {
    setFocusedLocation(location);
    setRangeOffset(Math.floor(location.offset / RANGE_SIZE) * RANGE_SIZE);
  }

  function updateFindingReview(findingId: string, review: FindingReview) {
    setFindingReviews((current) => ({ ...current, [findingId]: review }));
  }

  async function exportReview() {
    if (!analysisResult || reviewExporting) return;
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
      limitations: ["本地复核文件不包含原始字节，也不等同于已验证的协议结论。"],
    };
    setReviewExporting(true);
    setReviewExportError(null);
    setSessionNotice(null);
    try {
      const exportedName = await exportReviewJson(payload, analysisResult.taskId + "-review.json");
      setSessionNotice(exportedName ? "复核 JSON 已导出：" + exportedName : "已取消导出复核 JSON。");
    } catch (error) {
      setReviewExportError(error instanceof Error ? error.message : String(error));
    } finally {
      setReviewExporting(false);
    }
  }

  async function stopTask() {
    if (!taskId) return;
    try {
      await cancelTask(taskId);
    } catch (error) {
      setAnalysisError(error instanceof Error ? error.message : String(error));
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="比特流协议分析工作台">
          <BrandMark />
          <span>比特流分析</span>
        </a>
        <div className="topbar-actions">
          <span className="protocol-label">协议 v{update.protocolVersion}</span>
          <button className="settings-button" onClick={() => setSettingsOpen(true)}>
            <SettingsIcon />
            模型设置
            {llmStatus.configured && <span className="active-dot" />}
          </button>
        </div>
      </header>

      <div className="workspace" id="top">
        <aside className="sidebar">
          <div className="sidebar-heading">
            <p className="section-kicker">分析工作区</p>
            <h1>未知二进制流</h1>
            <p>导入本地数据，组合确定性算法与可选模型推理，并保留可追溯证据。</p>
          </div>

          <section className="sidebar-section">
            <div className="step-label"><span>1</span>选择数据</div>
            <button className="file-drop" onClick={() => void handleSelectInput()}>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16V4m0 0L8 8m4-4 4 4M5 14v5h14v-5" /></svg>
              <strong>{input ? "更换输入文件" : "选择二进制文件"}</strong>
              <small>.dat · .bin · .pcap · .pcapng</small>
            </button>
            {input && (
              <div className="file-summary">
                <div><span className="file-kind">{input.kind}</span><strong title={input.sourceName}>{input.sourceName}</strong></div>
                <dl>
                  <div><dt>大小</dt><dd>{formatBytes(input.sizeBytes)}</dd></div>
                  <div><dt>SHA-256</dt><dd title={input.sha256}>{input.sha256.slice(0, 12)}…</dd></div>
                </dl>
              </div>
            )}
            {inputError && <p className="error">{inputError}</p>}
          </section>

          <section className="sidebar-section">
            <div className="step-label"><span>2</span>选择分析方式</div>
            <label className={"model-option " + (llmStatus.configured ? "ready" : "")}>
              <div>
                <strong>模型辅助推理</strong>
                <small>{llmStatus.configured ? llmStatus.endpointHost + " · " + llmStatus.model : "尚未配置 OpenAI 兼容接口"}</small>
              </div>
              <input
                type="checkbox"
                checked={llmEnabled}
                disabled={!llmStatus.configured || isRunning}
                onChange={(event) => setLlmEnabled(event.target.checked)}
              />
            </label>
            {!llmStatus.configured && <button className="inline-action" onClick={() => setSettingsOpen(true)}>配置模型接口</button>}
            <p className="helper-copy">关闭时使用完全离线的确定性分析流程。</p>
          </section>

          <section className="sidebar-section action-section">
            <div className="step-label"><span>3</span>开始分析</div>
            <button className="primary wide start-button" disabled={isRunning || (llmEnabled && !input)} onClick={() => void runAnalysis()}>
              {isRunning ? stageName + "…" : "开始分析"}
            </button>
            <button className="secondary wide" disabled={!taskId || !isRunning} onClick={() => void stopTask()}>取消任务</button>
            <details className="developer-options">
              <summary>开发测试选项</summary>
              <label><input checked={failureMode} onChange={(event) => setFailureMode(event.target.checked)} type="checkbox" /> 模拟分析器失败</label>
            </details>
          </section>

          <div className="session-safety">
            <span className="safety-mark">i</span>
            <p>模型建议只是候选假设。只有通过证据关联和确定性验证的内容才会标记为已接受。</p>
          </div>
        </aside>

        <section className="main-column">
          <div className="page-intro">
            <div>
              <p className="section-kicker">本地协议分析</p>
              <h2>{input ? input.sourceName : "准备分析一个二进制流"}</h2>
            </div>
            <span className={"status-pill status-" + update.status.toLowerCase()}>{statusLabel[update.status]}</span>
          </div>

          {sessionNotice && <div className="session-notice" role="status">{sessionNotice}</div>}

          <section className="assistant-card">
            <div className="assistant-avatar"><BrandMark /></div>
            <div className="assistant-response">
              <div className="assistant-heading">
                <strong>分析助手</strong>
                <span>{llmEnabled ? "模型辅助 · " + (llmStatus.model || "") : "离线确定性分析"}</span>
              </div>
              <p>{assistantText}</p>
              {(isRunning || update.status === "COMPLETED") && (
                <div className="progress-row">
                  <div className="progress-track" aria-label={"任务进度 " + Math.round(update.progress * 100) + "%"}>
                    <div className="progress-value" style={{ width: (update.progress * 100) + "%" }} />
                  </div>
                  <span>{Math.round(update.progress * 100)}%</span>
                </div>
              )}
              {update.error && <p className="error error-box">{update.error.code}: {update.error.message}</p>}
            </div>
          </section>

          <section className="content-card overview-panel">
            <div className="section-heading">
              <div><h3>文件概览</h3><span>确定性扫描结果</span></div>
              {taskId && <span className="task-reference">{taskId}</span>}
            </div>
            {overviewError && <p className="error">{overviewError}</p>}
            {analysisError && <p className="error">结果读取失败：{analysisError}</p>}
            {!input && <div className="empty-state compact-empty"><strong>等待文件</strong><p>左侧选择文件后，这里会显示格式、大小、哈希和可用元数据。</p></div>}
            {input && overview && (
              <dl className="overview-grid">
                <div><dt>格式</dt><dd>{overview.kind}</dd></div>
                <div><dt>大小</dt><dd>{formatBytes(overview.sizeBytes)}</dd></div>
                <div><dt>方向信息</dt><dd>{overview.directionAvailable ? "可用" : "不可用"}</dd></div>
                <div><dt>时间戳</dt><dd>{overview.timestampAvailable ? "可用" : "不可用"}</dd></div>
                <div className="wide-fact"><dt>SHA-256</dt><dd>{overview.sha256}</dd></div>
              </dl>
            )}
          </section>

          <section className="content-card result-panel">
            <div className="section-heading result-heading">
              <div>
                <h3>分析结果</h3>
                <span>{analysisResult ? analysisResult.status + " · 结构化结果" : "等待分析结果"}</span>
              </div>
              <div className="result-actions">
                <button className="quiet-button" onClick={loadFixture}>载入合成示例</button>
                <button className="quiet-button" disabled={!analysisResult || reviewExporting} onClick={() => void exportReview()}>
                  {reviewExporting ? "正在导出…" : "导出复核 JSON"}
                </button>
              </div>
            </div>
            {reviewExportError && <p className="error">导出复核 JSON 失败：{reviewExportError}</p>}
            {analysisResult && <p className="review-summary">已在本地复核 {Object.keys(findingReviews).length} / {analysisResult.findings.length} 条结论；分析器原始状态保持不变。</p>}
            <AnalysisTabs active={activeView} onChange={setActiveView} hasResult={analysisResult !== null} />
            {focusedLocation && (
              <p className="focus-note">Hex 定位：{focusedLocation.inputId} @ +{focusedLocation.offset}（{focusedLocation.length} 字节）</p>
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

          <section className="event-strip" aria-label="最近任务事件">
            <span>最近事件</span>
            <p>{statusLabel[update.status]} · {stageName}</p>
          </section>
        </section>
      </div>

      <ModelSettingsDrawer
        open={settingsOpen}
        busy={isRunning}
        configured={llmStatus.configured}
        currentHost={llmStatus.endpointHost}
        currentModel={llmStatus.model}
        onClose={() => setSettingsOpen(false)}
        onSave={handleConfigureLlm}
        onClear={handleClearLlm}
      />
    </main>
  );
}
