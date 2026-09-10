from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_count(text: str, old: str, new: str, expected: int, label: str) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} matches, found {count}")
    return text.replace(old, new)


def patch_rust() -> None:
    path = ROOT / "apps" / "desktop" / "src-tauri" / "src" / "main.rs"
    text = path.read_text(encoding="utf-8")

    old_state = '''#[derive(Clone)]
struct AppState {
    tasks: Arc<Mutex<HashMap<String, TaskLifecycle>>>,
    sidecar: Arc<Mutex<Option<SidecarClient>>>,
    next_id: Arc<AtomicU64>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum TaskLifecycle {
    Running,
    Cancelled,
    Finished,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            tasks: Arc::new(Mutex::new(HashMap::new())),
            sidecar: Arc::new(Mutex::new(None)),
            next_id: Arc::new(AtomicU64::new(1)),
        }
    }
}
'''
    new_state = '''#[derive(Clone)]
struct AppState {
    tasks: Arc<Mutex<HashMap<String, TaskLifecycle>>>,
    sidecar: Arc<Mutex<Option<SidecarClient>>>,
    llm_config: Arc<Mutex<LlmRuntimeConfig>>,
    next_id: Arc<AtomicU64>,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum TaskLifecycle {
    Running,
    Cancelled,
    Finished,
}

#[derive(Clone)]
struct LlmRuntimeConfig {
    enabled: bool,
    endpoint: String,
    model: String,
    api_key_env: String,
    api_key: Option<String>,
    structured_output: String,
    timeout_seconds: u64,
}

#[derive(Clone, Deserialize)]
#[serde(rename_all = "camelCase")]
struct LlmSettingsInput {
    enabled: bool,
    endpoint: String,
    model: String,
    api_key: Option<String>,
    structured_output: String,
    timeout_seconds: u64,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct LlmSettingsView {
    enabled: bool,
    endpoint: String,
    model: String,
    structured_output: String,
    timeout_seconds: u64,
    has_api_key: bool,
}

impl Default for LlmRuntimeConfig {
    fn default() -> Self {
        let enabled = std::env::var("COURSE_PROJECT_LLM_ENABLED")
            .ok()
            .map(|value| matches!(value.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on"))
            .unwrap_or(false);
        let endpoint = std::env::var("COURSE_PROJECT_LLM_ENDPOINT").unwrap_or_default();
        let model = std::env::var("COURSE_PROJECT_LLM_MODEL").unwrap_or_default();
        let api_key_env = std::env::var("COURSE_PROJECT_LLM_API_KEY_ENV")
            .unwrap_or_else(|_| "COURSE_PROJECT_LLM_API_KEY".to_string());
        let api_key = std::env::var(&api_key_env)
            .ok()
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());
        let structured_output = match std::env::var("COURSE_PROJECT_LLM_STRUCTURED_OUTPUT")
            .unwrap_or_else(|_| "json_object".to_string())
            .as_str()
        {
            "prompt_only" => "prompt_only".to_string(),
            _ => "json_object".to_string(),
        };
        let timeout_seconds = std::env::var("COURSE_PROJECT_LLM_TIMEOUT_SECONDS")
            .ok()
            .and_then(|value| value.parse::<u64>().ok())
            .filter(|value| (1..=300).contains(value))
            .unwrap_or(30);
        Self {
            enabled,
            endpoint,
            model,
            api_key_env,
            api_key,
            structured_output,
            timeout_seconds,
        }
    }
}

impl LlmRuntimeConfig {
    fn view(&self) -> LlmSettingsView {
        LlmSettingsView {
            enabled: self.enabled,
            endpoint: self.endpoint.clone(),
            model: self.model.clone(),
            structured_output: self.structured_output.clone(),
            timeout_seconds: self.timeout_seconds,
            has_api_key: self.api_key.is_some(),
        }
    }

    fn updated(&self, input: LlmSettingsInput) -> Result<Self, String> {
        let endpoint = input.endpoint.trim().to_string();
        let model = input.model.trim().to_string();
        if !matches!(input.structured_output.as_str(), "json_object" | "prompt_only") {
            return Err("structured output must be json_object or prompt_only".to_string());
        }
        if !(1..=300).contains(&input.timeout_seconds) {
            return Err("LLM timeout must be between 1 and 300 seconds".to_string());
        }
        let supplied_key = input
            .api_key
            .map(|value| value.trim().to_string())
            .filter(|value| !value.is_empty());
        let api_key = supplied_key.or_else(|| self.api_key.clone());
        if input.enabled {
            if !endpoint.starts_with("https://") {
                return Err("live LLM endpoint must use https://".to_string());
            }
            if model.is_empty() {
                return Err("live LLM model must not be empty".to_string());
            }
            if api_key.is_none() {
                return Err("live LLM API key is required".to_string());
            }
        }
        Ok(Self {
            enabled: input.enabled,
            endpoint,
            model,
            api_key_env: "COURSE_PROJECT_LLM_API_KEY".to_string(),
            api_key,
            structured_output: input.structured_output,
            timeout_seconds: input.timeout_seconds,
        })
    }
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            tasks: Arc::new(Mutex::new(HashMap::new())),
            sidecar: Arc::new(Mutex::new(None)),
            llm_config: Arc::new(Mutex::new(LlmRuntimeConfig::default())),
            next_id: Arc::new(AtomicU64::new(1)),
        }
    }
}
'''
    text = replace_once(text, old_state, new_state, "rust app state")

    old_drop = '''impl Drop for SidecarClient {
'''
    new_drop = '''fn apply_llm_environment(command: &mut Command, config: &LlmRuntimeConfig) {
    command.env(
        "COURSE_PROJECT_LLM_ENABLED",
        if config.enabled { "1" } else { "0" },
    );
    command.env("COURSE_PROJECT_LLM_ENDPOINT", &config.endpoint);
    command.env("COURSE_PROJECT_LLM_MODEL", &config.model);
    command.env("COURSE_PROJECT_LLM_API_KEY_ENV", &config.api_key_env);
    command.env(
        "COURSE_PROJECT_LLM_STRUCTURED_OUTPUT",
        &config.structured_output,
    );
    command.env(
        "COURSE_PROJECT_LLM_TIMEOUT_SECONDS",
        config.timeout_seconds.to_string(),
    );
    if let Some(api_key) = &config.api_key {
        command.env(&config.api_key_env, api_key);
    }
}

fn spawn_sidecar_for_state(state: &AppState) -> Result<SidecarClient, String> {
    let config = state
        .llm_config
        .lock()
        .map_err(|_| "LLM configuration state is unavailable".to_string())?
        .clone();
    SidecarClient::spawn_with_config(&config)
}

impl Drop for SidecarClient {
'''
    text = replace_once(text, old_drop, new_drop, "rust sidecar env helpers")

    old_spawn = '''impl SidecarClient {
    fn spawn() -> Result<Self, String> {
        let state_dir = sidecar_state_dir()?;
'''
    new_spawn = '''impl SidecarClient {
    #[cfg(test)]
    fn spawn() -> Result<Self, String> {
        Self::spawn_with_config(&LlmRuntimeConfig::default())
    }

    fn spawn_with_config(config: &LlmRuntimeConfig) -> Result<Self, String> {
        let state_dir = sidecar_state_dir()?;
'''
    text = replace_once(text, old_spawn, new_spawn, "rust sidecar spawn")
    text = replace_once(
        text,
        '''        let mut command = Command::new(program);
        command.args(args);
        if python_mode {
''',
        '''        let mut command = Command::new(program);
        command.args(args);
        apply_llm_environment(&mut command, config);
        if python_mode {
''',
        "rust child environment",
    )
    text = replace_count(
        text,
        '''        *guard = Some(SidecarClient::spawn()?);
''',
        '''        *guard = Some(spawn_sidecar_for_state(state)?);
''',
        3,
        "rust app sidecar spawn sites",
    )

    text = replace_once(
        text,
        '''fn run_sidecar_analysis(
    app: &AppHandle,
    state: &AppState,
    task_id: &str,
    input_ref: &str,
) -> Result<(), String> {
    let params = json!({
''',
        '''fn run_sidecar_analysis(
    app: &AppHandle,
    state: &AppState,
    task_id: &str,
    input_ref: &str,
) -> Result<(), String> {
    let llm_enabled = state
        .llm_config
        .lock()
        .map_err(|_| "LLM configuration state is unavailable".to_string())?
        .enabled;
    let params = json!({
''',
        "rust analysis config read",
    )
    text = replace_once(
        text,
        '''        "llmEnabled": false,
        "verificationEnabled": true,
''',
        '''        "llmEnabled": llm_enabled,
        "verificationEnabled": true,
''',
        "rust analysis llm flag",
    )

    commands = '''#[tauri::command]
fn get_llm_settings(state: State<'_, AppState>) -> Result<LlmSettingsView, String> {
    state
        .llm_config
        .lock()
        .map_err(|_| "LLM configuration state is unavailable".to_string())
        .map(|config| config.view())
}

#[tauri::command]
fn configure_llm_settings(
    settings: LlmSettingsInput,
    state: State<'_, AppState>,
) -> Result<LlmSettingsView, String> {
    let running = state
        .tasks
        .lock()
        .map_err(|_| "task state is unavailable".to_string())?
        .values()
        .any(|lifecycle| *lifecycle == TaskLifecycle::Running);
    if running {
        return Err("cannot change LLM settings while an analysis task is running".to_string());
    }

    let view = {
        let mut current = state
            .llm_config
            .lock()
            .map_err(|_| "LLM configuration state is unavailable".to_string())?;
        let updated = current.updated(settings)?;
        let view = updated.view();
        *current = updated;
        view
    };

    *state
        .sidecar
        .lock()
        .map_err(|_| "sidecar state is unavailable".to_string())? = None;
    Ok(view)
}

'''
    text = replace_once(
        text,
        '''#[tauri::command]
fn get_analysis_result(task_id: String, state: State<'_, AppState>) -> Result<Value, String> {
''',
        commands + '''#[tauri::command]
fn get_analysis_result(task_id: String, state: State<'_, AppState>) -> Result<Value, String> {
''',
        "rust LLM settings commands",
    )

    text = replace_once(
        text,
        '''        bundled_sidecar_candidates, cancel_task_if_running, find_restored_artifact,
        finish_task_if_running, read_artifact_preview, resolve_controlled_path, AppState,
        SidecarClient, TaskLifecycle, SIDECAR_EXECUTABLE_NAME,
''',
        '''        bundled_sidecar_candidates, cancel_task_if_running, find_restored_artifact,
        finish_task_if_running, read_artifact_preview, resolve_controlled_path, AppState,
        LlmRuntimeConfig, LlmSettingsInput, SidecarClient, TaskLifecycle,
        SIDECAR_EXECUTABLE_NAME,
''',
        "rust test imports",
    )

    llm_test = '''    #[test]
    fn llm_runtime_settings_validate_live_configuration_and_preserve_secret() {
        let base = LlmRuntimeConfig {
            enabled: false,
            endpoint: String::new(),
            model: String::new(),
            api_key_env: "COURSE_PROJECT_LLM_API_KEY".to_string(),
            api_key: Some("existing-secret".to_string()),
            structured_output: "json_object".to_string(),
            timeout_seconds: 30,
        };
        let configured = base
            .updated(LlmSettingsInput {
                enabled: true,
                endpoint: "https://llm.example.test/v1/chat/completions".to_string(),
                model: "test-model".to_string(),
                api_key: None,
                structured_output: "prompt_only".to_string(),
                timeout_seconds: 60,
            })
            .expect("existing in-memory secret should be reusable");
        assert!(configured.enabled);
        assert_eq!(configured.model, "test-model");
        assert_eq!(configured.api_key.as_deref(), Some("existing-secret"));
        assert_eq!(configured.structured_output, "prompt_only");
        assert!(base
            .updated(LlmSettingsInput {
                enabled: true,
                endpoint: "http://insecure.example/v1/chat/completions".to_string(),
                model: "test-model".to_string(),
                api_key: Some("secret".to_string()),
                structured_output: "json_object".to_string(),
                timeout_seconds: 30,
            })
            .is_err());
    }

'''
    text = replace_once(
        text,
        '''    #[test]
    fn task_lifecycle_keeps_cancellation_terminal() {
''',
        llm_test + '''    #[test]
    fn task_lifecycle_keeps_cancellation_terminal() {
''',
        "rust LLM settings test",
    )

    text = replace_once(
        text,
        '''            cancel_contract_spike,
            select_input,
            inspect_file,
''',
        '''            cancel_contract_spike,
            get_llm_settings,
            configure_llm_settings,
            select_input,
            inspect_file,
''',
        "rust command registration",
    )
    path.write_text(text, encoding="utf-8")


def patch_gateway() -> None:
    path = ROOT / "apps" / "desktop" / "src" / "taskGateway.ts"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''export interface RestoredArtifactPreview {
  artifactId: string;
  format: ArtifactRef["format"];
  totalBytes: number;
  previewBytes: number;
  eof: boolean;
  bytes: number[];
  text?: string;
}
''',
        '''export interface RestoredArtifactPreview {
  artifactId: string;
  format: ArtifactRef["format"];
  totalBytes: number;
  previewBytes: number;
  eof: boolean;
  bytes: number[];
  text?: string;
}

export interface LlmSettings {
  enabled: boolean;
  endpoint: string;
  model: string;
  structuredOutput: "json_object" | "prompt_only";
  timeoutSeconds: number;
  hasApiKey: boolean;
}

export interface LlmSettingsInput {
  enabled: boolean;
  endpoint: string;
  model: string;
  apiKey?: string;
  structuredOutput: "json_object" | "prompt_only";
  timeoutSeconds: number;
}
''',
        "gateway LLM types",
    )
    text = replace_once(
        text,
        '''export function isDesktopRuntime() {
  return hasTauriRuntime();
}
''',
        '''export function isDesktopRuntime() {
  return hasTauriRuntime();
}

export async function getLlmSettings(): Promise<LlmSettings> {
  if (!hasTauriRuntime()) {
    return {
      enabled: false,
      endpoint: "",
      model: "",
      structuredOutput: "json_object",
      timeoutSeconds: 30,
      hasApiKey: false,
    };
  }
  return invoke<LlmSettings>("get_llm_settings");
}

export async function configureLlmSettings(settings: LlmSettingsInput): Promise<LlmSettings> {
  if (!hasTauriRuntime()) throw new Error("Live LLM settings require the Tauri desktop runtime.");
  return invoke<LlmSettings>("configure_llm_settings", { settings });
}
''',
        "gateway LLM functions",
    )
    path.write_text(text, encoding="utf-8")


def patch_app() -> None:
    path = ROOT / "apps" / "desktop" / "src" / "App.tsx"
    text = path.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''  cancelTask,
  getAnalysisResult,
  inspectInput,
''',
        '''  cancelTask,
  configureLlmSettings,
  getAnalysisResult,
  getLlmSettings,
  inspectInput,
''',
        "app gateway imports",
    )
    text = replace_once(
        text,
        '''  type InputMetadata,
  type RangeData,
''',
        '''  type InputMetadata,
  type LlmSettings,
  type RangeData,
''',
        "app LLM type import",
    )
    text = replace_once(
        text,
        '''const RANGE_SIZE = 256;
''',
        '''const RANGE_SIZE = 256;
const defaultLlmSettings: LlmSettings = {
  enabled: false,
  endpoint: "",
  model: "",
  structuredOutput: "json_object",
  timeoutSeconds: 30,
  hasApiKey: false,
};
''',
        "app LLM defaults",
    )
    text = replace_once(
        text,
        '''  const [findingReviews, setFindingReviews] = useState<Record<string, FindingReview>>({});

  useEffect(() => {
''',
        '''  const [findingReviews, setFindingReviews] = useState<Record<string, FindingReview>>({});
  const [llmSettings, setLlmSettings] = useState<LlmSettings>(defaultLlmSettings);
  const [llmEndpoint, setLlmEndpoint] = useState("");
  const [llmModel, setLlmModel] = useState("");
  const [llmApiKey, setLlmApiKey] = useState("");
  const [llmStructuredOutput, setLlmStructuredOutput] = useState<"json_object" | "prompt_only">("json_object");
  const [llmTimeoutSeconds, setLlmTimeoutSeconds] = useState(30);
  const [llmSettingsError, setLlmSettingsError] = useState<string | null>(null);
  const [llmSettingsMessage, setLlmSettingsMessage] = useState<string | null>(null);
  const [savingLlmSettings, setSavingLlmSettings] = useState(false);

  useEffect(() => {
    if (!isDesktopRuntime()) return;
    let active = true;
    void getLlmSettings()
      .then((settings) => {
        if (!active) return;
        setLlmSettings(settings);
        setLlmEndpoint(settings.endpoint);
        setLlmModel(settings.model);
        setLlmStructuredOutput(settings.structuredOutput);
        setLlmTimeoutSeconds(settings.timeoutSeconds);
      })
      .catch((error: unknown) => {
        if (active) setLlmSettingsError(error instanceof Error ? error.message : String(error));
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
''',
        "app LLM state and load",
    )

    save_function = '''  async function saveLlmConfiguration() {
    if (!isDesktopRuntime()) {
      setLlmSettingsError("Live LLM settings require the Tauri desktop runtime.");
      return;
    }
    setSavingLlmSettings(true);
    setLlmSettingsError(null);
    setLlmSettingsMessage(null);
    try {
      const saved = await configureLlmSettings({
        enabled: llmSettings.enabled,
        endpoint: llmEndpoint,
        model: llmModel,
        apiKey: llmApiKey.trim() || undefined,
        structuredOutput: llmStructuredOutput,
        timeoutSeconds: llmTimeoutSeconds,
      });
      setLlmSettings(saved);
      setLlmApiKey("");
      setInput(null);
      setOverview(null);
      setRange(null);
      setRangeOffset(0);
      setTaskId(null);
      setAnalysisResult(null);
      setFindingReviews({});
      setUpdate({
        ...initialUpdate,
        message: saved.enabled
          ? `Live LLM configured for ${saved.model}. Re-select the input before analysis.`
          : "Live LLM disabled. Re-select the input before analysis.",
      });
      setLlmSettingsMessage("Settings applied to a fresh Sidecar session. Re-select the input before starting analysis.");
    } catch (error) {
      setLlmSettingsError(error instanceof Error ? error.message : String(error));
    } finally {
      setSavingLlmSettings(false);
    }
  }

'''
    text = replace_once(
        text,
        '''  async function handleSelectInput() {
''',
        save_function + '''  async function handleSelectInput() {
''',
        "app LLM save handler",
    )

    llm_panel = '''
          <div className="llm-settings-block">
            <div className="subheading"><h3>Live LLM</h3><span>{llmSettings.enabled ? "enabled" : "offline"}</span></div>
            <label className="toggle-row">
              <input
                checked={llmSettings.enabled}
                disabled={savingLlmSettings || isRunning}
                onChange={(event) => setLlmSettings((current) => ({ ...current, enabled: event.target.checked }))}
                type="checkbox"
              />
              Use OpenAI-compatible live model
            </label>
            <div className="llm-settings-grid">
              <label>
                Endpoint
                <input
                  disabled={savingLlmSettings || isRunning}
                  onChange={(event) => setLlmEndpoint(event.target.value)}
                  placeholder="https://provider.example/v1/chat/completions"
                  spellCheck={false}
                  type="url"
                  value={llmEndpoint}
                />
              </label>
              <label>
                Model
                <input
                  disabled={savingLlmSettings || isRunning}
                  onChange={(event) => setLlmModel(event.target.value)}
                  placeholder="model-id"
                  spellCheck={false}
                  value={llmModel}
                />
              </label>
              <label>
                API key
                <input
                  autoComplete="off"
                  disabled={savingLlmSettings || isRunning}
                  onChange={(event) => setLlmApiKey(event.target.value)}
                  placeholder={llmSettings.hasApiKey ? "Configured — leave blank to keep" : "Required when enabled"}
                  type="password"
                  value={llmApiKey}
                />
              </label>
              <label>
                Structured output
                <select
                  disabled={savingLlmSettings || isRunning}
                  onChange={(event) => setLlmStructuredOutput(event.target.value as "json_object" | "prompt_only")}
                  value={llmStructuredOutput}
                >
                  <option value="json_object">json_object</option>
                  <option value="prompt_only">prompt_only</option>
                </select>
              </label>
              <label>
                Timeout (s)
                <input
                  disabled={savingLlmSettings || isRunning}
                  max={300}
                  min={1}
                  onChange={(event) => setLlmTimeoutSeconds(Number(event.target.value))}
                  type="number"
                  value={llmTimeoutSeconds}
                />
              </label>
            </div>
            <button
              className="secondary llm-save"
              disabled={savingLlmSettings || isRunning}
              onClick={() => void saveLlmConfiguration()}
            >
              {savingLlmSettings ? "Applying…" : "Apply LLM settings"}
            </button>
            <p className="settings-note">API keys stay in Rust/Sidecar process memory for this app session and are never returned to the WebView after save.</p>
            {llmSettingsMessage && <p className="settings-success">{llmSettingsMessage}</p>}
            {llmSettingsError && <p className="error">{llmSettingsError}</p>}
          </div>
'''
    text = replace_once(
        text,
        '''
          <div className="task-actions">
''',
        llm_panel + '''
          <div className="task-actions">
''',
        "app LLM settings panel",
    )
    path.write_text(text, encoding="utf-8")


def patch_styles() -> None:
    path = ROOT / "apps" / "desktop" / "src" / "styles.css"
    text = path.read_text(encoding="utf-8")
    marker = ".llm-settings-block {"
    if marker in text:
        raise RuntimeError("styles already contain LLM settings block")
    text += '''

.llm-settings-block {
  border-top: 1px solid #30342f;
  margin-top: 1.2rem;
  padding-top: 1rem;
}

.llm-settings-grid {
  display: grid;
  gap: 0.65rem;
  margin-top: 0.8rem;
}

.llm-settings-grid label {
  color: #99a196;
  display: grid;
  font-size: 0.65rem;
  gap: 0.3rem;
  text-transform: uppercase;
}

.llm-settings-grid input,
.llm-settings-grid select {
  background: #070806;
  border: 1px solid #51564e;
  border-radius: 0;
  box-sizing: border-box;
  color: #e6e8e4;
  min-width: 0;
  padding: 0.55rem 0.6rem;
  width: 100%;
}

.llm-settings-grid input:focus,
.llm-settings-grid select:focus {
  border-color: #c6ff4a;
  outline: none;
}

.llm-save {
  margin-top: 0.75rem;
  width: 100%;
}

.settings-note,
.settings-success {
  font-size: 0.67rem;
  line-height: 1.5;
  margin: 0.65rem 0 0;
}

.settings-note { color: #99a196; }
.settings-success { color: #c6ff4a; }
'''
    path.write_text(text, encoding="utf-8")


def patch_docs() -> None:
    path = ROOT / "docs" / "llm-live-provider.md"
    text = path.read_text(encoding="utf-8")
    old = '''The desktop application keeps its frozen request offline-safe, but the CLI/packaged Sidecar now supports an explicit process-level opt-in through `COURSE_PROJECT_LLM_ENABLED=1`. When that variable is enabled, the Sidecar upgrades the effective semantic configuration to `llmEnabled=true`; when it is absent or false, the existing deterministic behavior is unchanged. Invalid enable values fail closed instead of silently enabling network access.
'''
    new = '''The desktop application is offline-safe by default. The Tauri UI now exposes an explicit Live LLM settings block for endpoint, model, API key, structured-output mode and timeout. Applying those settings restarts the controlled Sidecar and requires the input to be re-selected; the API key is held only in Rust/child-process memory and is never returned to the WebView after save. The CLI/packaged Sidecar also supports the process-level opt-in `COURSE_PROJECT_LLM_ENABLED=1`. When live mode is enabled, the effective semantic request uses `llmEnabled=true`; otherwise the deterministic behavior is unchanged.
'''
    text = replace_once(text, old, new, "live LLM desktop docs")
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_rust()
    patch_gateway()
    patch_app()
    patch_styles()
    patch_docs()


if __name__ == "__main__":
    main()
