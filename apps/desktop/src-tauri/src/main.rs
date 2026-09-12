mod review_export;

use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs::{self, File},
    io::{BufRead, BufReader, Read, Write},
    path::{Component, Path, PathBuf},
    process::{Child, ChildStdin, ChildStdout, Command, Stdio},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, State};
use tauri_plugin_dialog::DialogExt;

const TASK_EVENT: &str = "task-update";
const MAX_RESTORED_PREVIEW_BYTES: u64 = 64 * 1024;
const SIDECAR_EXECUTABLE_NAME: &str = "course-project-sidecar";

#[derive(Clone)]
struct AppState {
    tasks: Arc<Mutex<HashMap<String, TaskLifecycle>>>,
    sidecar: Arc<Mutex<Option<SidecarClient>>>,
    next_id: Arc<AtomicU64>,
    llm_config: Arc<Mutex<Option<LlmSessionConfig>>>,
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
            llm_config: Arc::new(Mutex::new(None)),
        }
    }
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct TaskError {
    code: String,
    message: String,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct TaskUpdate {
    protocol_version: u8,
    id: String,
    event: String,
    status: String,
    stage: String,
    progress: f32,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<TaskError>,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct InputMetadata {
    input_ref: String,
    kind: String,
    size_bytes: u64,
    sha256: String,
    source_name: String,
    direction_available: bool,
    timestamp_available: bool,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(rename_all = "camelCase")]
struct RangeData {
    input_ref: String,
    offset: u64,
    requested_length: u64,
    actual_length: u64,
    encoding: String,
    bytes: String,
    eof: bool,
}

#[derive(Clone)]
struct LlmSessionConfig {
    endpoint: String,
    model: String,
    api_key: String,
    structured_output: String,
}

#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct LlmSessionSettings {
    endpoint: String,
    model: String,
    api_key: String,
    structured_output: String,
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct LlmConfigurationStatus {
    configured: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    endpoint_host: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    model: Option<String>,
    input_reselection_required: bool,
}

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RestoredArtifactPreview {
    artifact_id: String,
    format: String,
    total_bytes: u64,
    preview_bytes: u64,
    eof: bool,
    bytes: Vec<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    text: Option<String>,
}

#[derive(Clone)]
struct RestoredArtifactDescriptor {
    artifact_id: String,
    format: String,
    controlled_ref: String,
}

struct SidecarClient {
    _child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

enum SidecarLaunch {
    Bundled(PathBuf),
    Python(PathBuf),
}

fn sidecar_state_dir() -> Result<PathBuf, String> {
    let configured = std::env::var_os("COURSE_PROJECT_STATE_DIR").map(PathBuf::from);
    let path = if let Some(path) = configured {
        path
    } else if !cfg!(debug_assertions) {
        std::env::var_os("LOCALAPPDATA")
            .map(PathBuf::from)
            .map(|path| path.join("Evidence Workbench").join("state"))
            .unwrap_or_else(|| PathBuf::from(".course-project-state"))
    } else {
        PathBuf::from(".course-project-state")
    };
    if path.is_absolute() {
        Ok(path)
    } else {
        std::env::current_dir()
            .map(|current| current.join(path))
            .map_err(|error| format!("cannot resolve sidecar state directory: {error}"))
    }
}

fn bundled_sidecar_candidates(current_executable: &Path) -> Vec<PathBuf> {
    let extension = std::env::consts::EXE_EXTENSION;
    let filename = if extension.is_empty() {
        SIDECAR_EXECUTABLE_NAME.to_string()
    } else {
        format!("{SIDECAR_EXECUTABLE_NAME}.{extension}")
    };
    let Some(parent) = current_executable.parent() else {
        return Vec::new();
    };
    let mut candidates = vec![parent.join(&filename)];
    if parent.file_name().and_then(|name| name.to_str()) == Some("deps") {
        if let Some(debug_or_release) = parent.parent() {
            candidates.push(debug_or_release.join(filename));
        }
    }
    candidates
}

fn resolve_sidecar_launch() -> Result<SidecarLaunch, String> {
    if let Some(configured) = std::env::var_os("COURSE_PROJECT_SIDECAR_EXECUTABLE") {
        let path = PathBuf::from(configured);
        if !path.is_file() {
            return Err(format!(
                "configured packaged sidecar does not exist: {}",
                path.display()
            ));
        }
        return Ok(SidecarLaunch::Bundled(path));
    }

    if let Ok(current_executable) = std::env::current_exe() {
        if let Some(path) = bundled_sidecar_candidates(&current_executable)
            .into_iter()
            .find(|candidate| candidate.is_file())
        {
            return Ok(SidecarLaunch::Bundled(path));
        }
    }

    let python = std::env::var_os("COURSE_PROJECT_SIDECAR_COMMAND")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("python"));
    Ok(SidecarLaunch::Python(python))
}

impl Drop for SidecarClient {
    fn drop(&mut self) {
        let _ = self._child.kill();
        let _ = self._child.wait();
    }
}

impl SidecarClient {
    fn spawn(llm_config: Option<&LlmSessionConfig>) -> Result<Self, String> {
        let state_dir = sidecar_state_dir()?;
        fs::create_dir_all(&state_dir)
            .map_err(|error| format!("cannot create sidecar state directory: {error}"))?;
        let launch = resolve_sidecar_launch()?;
        let (program, args, python_mode) = match launch {
            SidecarLaunch::Bundled(program) => (
                program,
                vec!["--state-dir".into(), state_dir.as_os_str().to_owned()],
                false,
            ),
            SidecarLaunch::Python(program) => (
                program,
                vec![
                    "-m".into(),
                    "course_project.sidecar".into(),
                    "--state-dir".into(),
                    state_dir.as_os_str().to_owned(),
                ],
                true,
            ),
        };
        let program_display = program.display().to_string();
        let mut command = Command::new(program);
        command.args(args);
        if let Some(config) = llm_config {
            command
                .env("COURSE_PROJECT_LLM_ENDPOINT", &config.endpoint)
                .env("COURSE_PROJECT_LLM_MODEL", &config.model)
                .env("COURSE_PROJECT_LLM_API_KEY", &config.api_key)
                .env(
                    "COURSE_PROJECT_LLM_STRUCTURED_OUTPUT",
                    &config.structured_output,
                );
        }
        if python_mode {
            let mut python_paths = vec![Path::new(env!("CARGO_MANIFEST_DIR"))
                .ancestors()
                .nth(3)
                .unwrap_or_else(|| Path::new("."))
                .join("src")];
            if let Some(existing) = std::env::var_os("PYTHONPATH") {
                python_paths.extend(std::env::split_paths(&existing));
            }
            let python_path = std::env::join_paths(python_paths)
                .map_err(|error| format!("cannot prepare sidecar PYTHONPATH: {error}"))?;
            command.env("PYTHONPATH", python_path);
        }
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| format!("cannot start sidecar {program_display}: {error}"))?;
        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "sidecar stdin unavailable".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "sidecar stdout unavailable".to_string())?;
        Ok(Self {
            _child: child,
            stdin,
            stdout: BufReader::new(stdout),
            next_id: 1,
        })
    }

    fn request_messages_with_id(
        &mut self,
        request_id: &str,
        method: &str,
        params: Value,
    ) -> Result<Vec<Value>, String> {
        let message =
            json!({"protocolVersion": 1, "id": request_id, "method": method, "params": params});
        serde_json::to_writer(&mut self.stdin, &message)
            .map_err(|error| format!("cannot encode sidecar request: {error}"))?;
        self.stdin
            .write_all(b"\n")
            .map_err(|error| format!("cannot write sidecar request: {error}"))?;
        self.stdin
            .flush()
            .map_err(|error| format!("cannot flush sidecar request: {error}"))?;

        let mut responses = Vec::new();
        loop {
            let mut line = String::new();
            let count = self
                .stdout
                .read_line(&mut line)
                .map_err(|error| format!("cannot read sidecar response: {error}"))?;
            if count == 0 {
                return Err("sidecar exited without a response".to_string());
            }
            let response: Value = serde_json::from_str(&line)
                .map_err(|error| format!("invalid sidecar JSON response: {error}"))?;
            if let Some(error) = response.get("error") {
                let code = error
                    .get("code")
                    .and_then(Value::as_str)
                    .unwrap_or("sidecar_failed");
                let message = error
                    .get("message")
                    .and_then(Value::as_str)
                    .unwrap_or("sidecar request failed");
                return Err(format!("{code}: {message}"));
            }
            let terminal = response.get("resultRef").and_then(Value::as_str).is_some();
            responses.push(response);
            if terminal {
                return Ok(responses);
            }
        }
    }

    fn request_result_ref(&mut self, task_id: &str) -> Result<String, String> {
        let id = format!("desktop-{}", self.next_id);
        self.next_id += 1;
        let message = json!({"protocolVersion": 1, "id": id, "method": "get_result", "params": {"taskId": task_id}});
        serde_json::to_writer(&mut self.stdin, &message)
            .map_err(|error| format!("cannot encode sidecar request: {error}"))?;
        self.stdin
            .write_all(b"\n")
            .map_err(|error| format!("cannot write sidecar request: {error}"))?;
        self.stdin
            .flush()
            .map_err(|error| format!("cannot flush sidecar request: {error}"))?;

        let mut line = String::new();
        let count = self
            .stdout
            .read_line(&mut line)
            .map_err(|error| format!("cannot read sidecar response: {error}"))?;
        if count == 0 {
            return Err("sidecar exited without a response".to_string());
        }
        let response: Value = serde_json::from_str(&line)
            .map_err(|error| format!("invalid sidecar JSON response: {error}"))?;
        if let Some(error) = response.get("error") {
            let code = error
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("sidecar_failed");
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("sidecar request failed");
            return Err(format!("{code}: {message}"));
        }
        response
            .get("resultRef")
            .and_then(Value::as_str)
            .map(str::to_owned)
            .ok_or_else(|| "analysis result is not ready".to_string())
    }

    fn request<T: DeserializeOwned>(&mut self, method: &str, params: Value) -> Result<T, String> {
        let id = format!("desktop-{}", self.next_id);
        self.next_id += 1;
        let message = json!({"protocolVersion": 1, "id": id, "method": method, "params": params});
        serde_json::to_writer(&mut self.stdin, &message)
            .map_err(|error| format!("cannot encode sidecar request: {error}"))?;
        self.stdin
            .write_all(b"\n")
            .map_err(|error| format!("cannot write sidecar request: {error}"))?;
        self.stdin
            .flush()
            .map_err(|error| format!("cannot flush sidecar request: {error}"))?;

        let mut line = String::new();
        let count = self
            .stdout
            .read_line(&mut line)
            .map_err(|error| format!("cannot read sidecar response: {error}"))?;
        if count == 0 {
            return Err("Python sidecar exited without a response".to_string());
        }
        let response: Value = serde_json::from_str(&line)
            .map_err(|error| format!("invalid sidecar JSON response: {error}"))?;
        if let Some(error) = response.get("error") {
            let code = error
                .get("code")
                .and_then(Value::as_str)
                .unwrap_or("sidecar_failed");
            let message = error
                .get("message")
                .and_then(Value::as_str)
                .unwrap_or("sidecar request failed");
            return Err(format!("{code}: {message}"));
        }
        let data = response
            .get("data")
            .cloned()
            .ok_or_else(|| "sidecar response has no data".to_string())?;
        serde_json::from_value(data)
            .map_err(|error| format!("invalid sidecar response data: {error}"))
    }
}

fn sidecar_request<T: DeserializeOwned>(
    state: &AppState,
    method: &str,
    params: Value,
) -> Result<T, String> {
    let llm_config = state
        .llm_config
        .lock()
        .map_err(|_| "model configuration is unavailable".to_string())?
        .clone();
    let mut guard = state
        .sidecar
        .lock()
        .map_err(|_| "sidecar state is unavailable".to_string())?;
    if guard.is_none() {
        *guard = Some(SidecarClient::spawn(llm_config.as_ref())?);
    }
    let result = guard
        .as_mut()
        .expect("sidecar initialized")
        .request(method, params);
    if result.is_err() {
        *guard = None;
    }
    result
}

#[tauri::command]
async fn select_input(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<InputMetadata>, String> {
    let (sender, receiver) = std::sync::mpsc::channel();
    app.dialog()
        .file()
        .add_filter("Binary traffic", &["dat", "bin", "pcap", "pcapng"])
        .set_title("Select authorized binary traffic input")
        .pick_file(move |file| {
            let _ = sender.send(file);
        });
    let selected = tauri::async_runtime::spawn_blocking(move || receiver.recv())
        .await
        .map_err(|error| format!("file dialog failed: {error}"))?
        .map_err(|error| format!("file dialog callback failed: {error}"))?;
    let Some(file) = selected else {
        return Ok(None);
    };
    let path = file
        .into_path()
        .map_err(|error| format!("cannot access selected input: {error:?}"))?;
    let source_ref = path.to_string_lossy().replace('\\', "/");
    let app_state = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        sidecar_request(
            &app_state,
            "register_input",
            json!({"sourceRef": source_ref}),
        )
    })
    .await
    .map_err(|error| format!("input registration failed: {error}"))?
    .map(Some)
}

#[tauri::command]
fn inspect_file(input_ref: String, state: State<'_, AppState>) -> Result<InputMetadata, String> {
    sidecar_request(
        state.inner(),
        "inspect_file",
        json!({"inputRef": input_ref}),
    )
}

#[tauri::command]
fn read_range(
    input_ref: String,
    offset: u64,
    length: u64,
    state: State<'_, AppState>,
) -> Result<RangeData, String> {
    if length == 0 || length > 1_048_576 {
        return Err("length must be between 1 and 1048576 bytes".to_string());
    }
    sidecar_request(
        state.inner(),
        "read_range",
        json!({"inputRef": input_ref, "offset": offset, "length": length}),
    )
}

fn validate_llm_settings(
    settings: LlmSessionSettings,
) -> Result<(LlmSessionConfig, String), String> {
    let endpoint = settings.endpoint.trim().to_string();
    let remainder = endpoint
        .strip_prefix("https://")
        .ok_or_else(|| "model endpoint must use HTTPS".to_string())?;
    let authority = remainder.split('/').next().unwrap_or_default();
    let endpoint_host = authority.to_string();
    if authority.is_empty()
        || authority.contains('@')
        || endpoint.contains('?')
        || endpoint.contains('#')
        || endpoint.chars().any(char::is_whitespace)
        || endpoint.len() > 2048
    {
        return Err("model endpoint is not a safe OpenAI-compatible HTTPS URL".to_string());
    }

    let model = settings.model.trim().to_string();
    if model.is_empty() || model.len() > 200 || model.chars().any(char::is_control) {
        return Err("model name must contain 1 to 200 printable characters".to_string());
    }
    let api_key = settings.api_key.trim().to_string();
    if api_key.is_empty() || api_key.len() > 8192 || api_key.chars().any(char::is_whitespace) {
        return Err("API key must be non-empty and contain no whitespace".to_string());
    }
    if !matches!(
        settings.structured_output.as_str(),
        "json_object" | "prompt_only"
    ) {
        return Err("unsupported structured output mode".to_string());
    }

    Ok((
        LlmSessionConfig {
            endpoint,
            model,
            api_key,
            structured_output: settings.structured_output,
        },
        endpoint_host,
    ))
}

#[tauri::command]
fn configure_llm(
    settings: Option<LlmSessionSettings>,
    state: State<'_, AppState>,
) -> Result<LlmConfigurationStatus, String> {
    let has_running_task = state
        .tasks
        .lock()
        .map_err(|_| "task state is unavailable".to_string())?
        .values()
        .any(|lifecycle| *lifecycle == TaskLifecycle::Running);
    if has_running_task {
        return Err("cannot change model settings while an analysis task is running".to_string());
    }

    let prepared = settings.map(validate_llm_settings).transpose()?;
    let endpoint_host = prepared.as_ref().map(|(_, host)| host.clone());
    let model = prepared.as_ref().map(|(config, _)| config.model.clone());
    let config = prepared.map(|(config, _)| config);
    let configured = config.is_some();
    *state
        .llm_config
        .lock()
        .map_err(|_| "model configuration is unavailable".to_string())? = config;

    let input_reselection_required = state
        .sidecar
        .lock()
        .map_err(|_| "sidecar state is unavailable".to_string())?
        .take()
        .is_some();

    Ok(LlmConfigurationStatus {
        configured,
        endpoint_host,
        model,
        input_reselection_required,
    })
}

fn emit_update(app: &AppHandle, update: TaskUpdate) {
    let _ = app.emit(TASK_EVENT, update);
}

fn task_is_cancelled(state: &AppState, task_id: &str) -> bool {
    state
        .tasks
        .lock()
        .map(|tasks| tasks.get(task_id) == Some(&TaskLifecycle::Cancelled))
        .unwrap_or(true)
}

fn finish_task_if_running(state: &AppState, task_id: &str) -> bool {
    let Ok(mut tasks) = state.tasks.lock() else {
        return false;
    };
    let Some(lifecycle) = tasks.get_mut(task_id) else {
        return false;
    };
    if *lifecycle != TaskLifecycle::Running {
        return false;
    }
    *lifecycle = TaskLifecycle::Finished;
    true
}

fn cancel_task_if_running(state: &AppState, task_id: &str) -> Result<bool, String> {
    let mut tasks = state
        .tasks
        .lock()
        .map_err(|_| "task state is unavailable".to_string())?;
    let lifecycle = tasks
        .get_mut(task_id)
        .ok_or_else(|| format!("unknown task: {task_id}"))?;
    if *lifecycle != TaskLifecycle::Running {
        return Ok(false);
    }
    *lifecycle = TaskLifecycle::Cancelled;
    Ok(true)
}

fn result_state_root() -> Result<PathBuf, String> {
    sidecar_state_dir()?
        .canonicalize()
        .map_err(|error| format!("cannot access sidecar state directory: {error}"))
}

fn resolve_controlled_path(root: &Path, controlled_ref: &str) -> Result<PathBuf, String> {
    let relative = Path::new(controlled_ref);
    if controlled_ref.is_empty()
        || controlled_ref.contains('\\')
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err("sidecar returned an unsafe controlled reference".to_string());
    }
    let target = root
        .join(relative)
        .canonicalize()
        .map_err(|error| format!("cannot access controlled result artifact: {error}"))?;
    if !target.starts_with(root) {
        return Err("sidecar artifact escapes the controlled state directory".to_string());
    }
    Ok(target)
}

fn read_controlled_result(result_ref: &str) -> Result<Value, String> {
    let root = result_state_root()?;
    let target = resolve_controlled_path(&root, result_ref)?;
    let content = fs::read_to_string(target)
        .map_err(|error| format!("cannot read controlled analysis result: {error}"))?;
    serde_json::from_str(&content).map_err(|error| format!("invalid analysis result JSON: {error}"))
}

fn request_task_result_ref(state: &AppState, task_id: &str) -> Result<String, String> {
    let llm_config = state
        .llm_config
        .lock()
        .map_err(|_| "model configuration is unavailable".to_string())?
        .clone();
    let mut guard = state
        .sidecar
        .lock()
        .map_err(|_| "sidecar state is unavailable".to_string())?;
    if guard.is_none() {
        *guard = Some(SidecarClient::spawn(llm_config.as_ref())?);
    }
    let result = guard
        .as_mut()
        .expect("sidecar initialized")
        .request_result_ref(task_id);
    if result.is_err() {
        *guard = None;
    }
    result
}

fn load_task_analysis_result(state: &AppState, task_id: &str) -> Result<Value, String> {
    let result_ref = request_task_result_ref(state, task_id)?;
    let result = read_controlled_result(&result_ref)?;
    if result.get("taskId").and_then(Value::as_str) != Some(task_id) {
        return Err("analysis result taskId does not match the requested task".to_string());
    }
    Ok(result)
}

fn find_restored_artifact(
    result: &Value,
    artifact_id: &str,
) -> Result<RestoredArtifactDescriptor, String> {
    if artifact_id.is_empty() {
        return Err("artifactId must not be empty".to_string());
    }
    let artifacts = result
        .get("artifacts")
        .and_then(Value::as_array)
        .ok_or_else(|| "analysis result contains no artifacts".to_string())?;
    let artifact = artifacts
        .iter()
        .find(|artifact| artifact.get("artifactId").and_then(Value::as_str) == Some(artifact_id))
        .ok_or_else(|| format!("unknown artifactId for this task: {artifact_id}"))?;
    if artifact.get("type").and_then(Value::as_str) != Some("restored") {
        return Err("only restored artifacts can be previewed or exported".to_string());
    }
    let format = artifact
        .get("format")
        .and_then(Value::as_str)
        .ok_or_else(|| "restored artifact has no format".to_string())?;
    let controlled_ref = artifact
        .get("ref")
        .and_then(Value::as_str)
        .ok_or_else(|| "restored artifact has no controlled ref".to_string())?;
    Ok(RestoredArtifactDescriptor {
        artifact_id: artifact_id.to_string(),
        format: format.to_string(),
        controlled_ref: controlled_ref.to_string(),
    })
}

fn read_artifact_preview(
    artifact: &RestoredArtifactDescriptor,
    path: &Path,
    length: u64,
) -> Result<RestoredArtifactPreview, String> {
    if length == 0 || length > MAX_RESTORED_PREVIEW_BYTES {
        return Err(format!(
            "length must be between 1 and {MAX_RESTORED_PREVIEW_BYTES} bytes"
        ));
    }
    let total_bytes = path
        .metadata()
        .map_err(|error| format!("cannot inspect restored artifact: {error}"))?
        .len();
    let mut bytes = Vec::with_capacity(length.min(total_bytes) as usize);
    File::open(path)
        .map_err(|error| format!("cannot open restored artifact: {error}"))?
        .take(length)
        .read_to_end(&mut bytes)
        .map_err(|error| format!("cannot read restored artifact preview: {error}"))?;
    let text_format = matches!(
        artifact.format.as_str(),
        "json" | "jsonl" | "csv" | "text" | "ksy"
    );
    let text = text_format.then(|| String::from_utf8_lossy(&bytes).into_owned());
    Ok(RestoredArtifactPreview {
        artifact_id: artifact.artifact_id.clone(),
        format: artifact.format.clone(),
        total_bytes,
        preview_bytes: bytes.len() as u64,
        eof: bytes.len() as u64 == total_bytes,
        bytes,
        text,
    })
}

fn run_sidecar_analysis(
    app: &AppHandle,
    state: &AppState,
    task_id: &str,
    input_ref: &str,
    llm_enabled: bool,
) -> Result<(), String> {
    let mode = if llm_enabled {
        "evidencegraph"
    } else {
        "baseline"
    };
    let stages = if llm_enabled {
        vec![
            "inspect",
            "features",
            "boundary",
            "inference",
            "evidence",
            "llm",
            "verification",
            "behavior",
        ]
    } else {
        vec![
            "inspect",
            "features",
            "boundary",
            "inference",
            "evidence",
            "verification",
            "behavior",
        ]
    };
    let params = json!({
        "inputRef": input_ref,
        "mode": mode,
        "stages": stages,
        "llmEnabled": llm_enabled,
        "verificationEnabled": true,
        "behaviorEnabled": true,
        "timeoutSeconds": 300,
        "optionalDependencyPolicy": "degrade"
    });
    emit_update(
        app,
        TaskUpdate {
            protocol_version: 1,
            id: task_id.to_string(),
            event: "progress".to_string(),
            status: "ANALYZING".to_string(),
            stage: "analysis".to_string(),
            progress: 0.0,
            message: "Sidecar analysis started".to_string(),
            error: None,
        },
    );

    let messages = {
        let llm_config = state
            .llm_config
            .lock()
            .map_err(|_| "model configuration is unavailable".to_string())?
            .clone();
        let mut guard = state
            .sidecar
            .lock()
            .map_err(|_| "sidecar state is unavailable".to_string())?;
        if guard.is_none() {
            *guard = Some(SidecarClient::spawn(llm_config.as_ref())?);
        }
        let result = guard
            .as_mut()
            .expect("sidecar initialized")
            .request_messages_with_id(task_id, "analyze", params);
        if result.is_err() {
            *guard = None;
        }
        result?
    };

    for message in messages {
        if task_is_cancelled(state, task_id) {
            return Ok(());
        }
        if let Some(progress) = message.get("progress").and_then(Value::as_f64) {
            let stage = message
                .get("stage")
                .and_then(Value::as_str)
                .unwrap_or("analysis");
            emit_update(
                app,
                TaskUpdate {
                    protocol_version: 1,
                    id: task_id.to_string(),
                    event: "progress".to_string(),
                    status: "ANALYZING".to_string(),
                    stage: stage.to_string(),
                    progress: progress as f32,
                    message: format!("Sidecar stage: {stage}"),
                    error: None,
                },
            );
        }
        if message.get("resultRef").and_then(Value::as_str).is_some() {
            if !finish_task_if_running(state, task_id) {
                return Ok(());
            }
            emit_update(
                app,
                TaskUpdate {
                    protocol_version: 1,
                    id: task_id.to_string(),
                    event: "status".to_string(),
                    status: "COMPLETED".to_string(),
                    stage: "completed".to_string(),
                    progress: 1.0,
                    message: "Sidecar analysis result is ready".to_string(),
                    error: None,
                },
            );
        }
    }
    Ok(())
}

#[tauri::command]
fn get_analysis_result(task_id: String, state: State<'_, AppState>) -> Result<Value, String> {
    load_task_analysis_result(state.inner(), &task_id)
}

#[tauri::command]
fn read_restored_artifact(
    task_id: String,
    artifact_id: String,
    length: u64,
    state: State<'_, AppState>,
) -> Result<RestoredArtifactPreview, String> {
    let result = load_task_analysis_result(state.inner(), &task_id)?;
    let artifact = find_restored_artifact(&result, &artifact_id)?;
    let root = result_state_root()?;
    let path = resolve_controlled_path(&root, &artifact.controlled_ref)?;
    read_artifact_preview(&artifact, &path, length)
}

#[tauri::command]
async fn export_restored_artifact(
    app: AppHandle,
    task_id: String,
    artifact_id: String,
    state: State<'_, AppState>,
) -> Result<Option<String>, String> {
    let result = load_task_analysis_result(state.inner(), &task_id)?;
    let artifact = find_restored_artifact(&result, &artifact_id)?;
    let root = result_state_root()?;
    let source = resolve_controlled_path(&root, &artifact.controlled_ref)?;
    if !source.is_file() {
        return Err("restored artifact is not a regular file".to_string());
    }
    let default_name = Path::new(&artifact.controlled_ref)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("restored-output.bin")
        .to_string();
    let (sender, receiver) = std::sync::mpsc::channel();
    app.dialog()
        .file()
        .set_title("Export restored artifact")
        .set_file_name(&default_name)
        .save_file(move |file| {
            let _ = sender.send(file);
        });
    let selected = tauri::async_runtime::spawn_blocking(move || receiver.recv())
        .await
        .map_err(|error| format!("file dialog failed: {error}"))?
        .map_err(|error| format!("file dialog callback failed: {error}"))?;
    let Some(file) = selected else {
        return Ok(None);
    };
    let destination = file
        .into_path()
        .map_err(|error| format!("cannot access export destination: {error:?}"))?;
    fs::copy(&source, &destination)
        .map_err(|error| format!("cannot export restored artifact: {error}"))?;
    let exported_name = destination
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("restored artifact")
        .to_string();
    Ok(Some(exported_name))
}

#[tauri::command]
fn start_contract_spike(
    app: AppHandle,
    state: State<'_, AppState>,
    failure_mode: bool,
    input_ref: Option<String>,
    llm_enabled: bool,
) -> Result<String, String> {
    if llm_enabled
        && state
            .llm_config
            .lock()
            .map_err(|_| "model configuration is unavailable".to_string())?
            .is_none()
    {
        return Err(
            "configure an OpenAI-compatible model before enabling LLM analysis".to_string(),
        );
    }
    let id = format!("contract-{}", state.next_id.fetch_add(1, Ordering::SeqCst));
    state
        .tasks
        .lock()
        .map_err(|_| "task state is unavailable".to_string())?
        .insert(id.clone(), TaskLifecycle::Running);

    let task_state = state.inner().clone();
    let task_id = id.clone();
    tauri::async_runtime::spawn(async move {
        if let Some(input_ref) = input_ref {
            if let Err(error) =
                run_sidecar_analysis(&app, &task_state, &task_id, &input_ref, llm_enabled)
            {
                if !finish_task_if_running(&task_state, &task_id) {
                    return;
                }
                emit_update(
                    &app,
                    TaskUpdate {
                        protocol_version: 1,
                        id: task_id.clone(),
                        event: "status".to_string(),
                        status: "FAILED".to_string(),
                        stage: "analysis".to_string(),
                        progress: 0.0,
                        message: "Sidecar analysis failed".to_string(),
                        error: Some(TaskError {
                            code: "sidecar_failed".to_string(),
                            message: error,
                        }),
                    },
                );
            }
            return;
        }

        let stages = [
            (
                "INSPECTING",
                "inspect_file",
                0.12,
                "Inspecting file contract",
            ),
            (
                "ANALYZING",
                "calculate_features",
                0.44,
                "Calculating byte-level features",
            ),
            (
                "ANALYZING",
                "detect_boundaries",
                0.72,
                "Scoring message boundaries",
            ),
            (
                "VERIFYING",
                "verify_hypotheses",
                0.90,
                "Preparing verification result",
            ),
            ("COMPLETED", "completed", 1.00, "Contract spike completed"),
        ];

        for (index, (status, stage, progress, message)) in stages.iter().enumerate() {
            std::thread::sleep(Duration::from_millis(650));
            if task_is_cancelled(&task_state, &task_id) {
                return;
            }

            if failure_mode && index == 2 {
                if !finish_task_if_running(&task_state, &task_id) {
                    return;
                }
                emit_update(
                    &app,
                    TaskUpdate {
                        protocol_version: 1,
                        id: task_id.clone(),
                        event: "status".to_string(),
                        status: "FAILED".to_string(),
                        stage: stage.to_string(),
                        progress: *progress,
                        message: "Mock analyzer stopped unexpectedly".to_string(),
                        error: Some(TaskError {
                            code: "mock_sidecar_failed".to_string(),
                            message: "Mock analyzer stopped unexpectedly".to_string(),
                        }),
                    },
                );
                return;
            }

            if *status == "COMPLETED" && !finish_task_if_running(&task_state, &task_id) {
                return;
            }

            emit_update(
                &app,
                TaskUpdate {
                    protocol_version: 1,
                    id: task_id.clone(),
                    event: if *status == "COMPLETED" {
                        "status"
                    } else {
                        "progress"
                    }
                    .to_string(),
                    status: status.to_string(),
                    stage: stage.to_string(),
                    progress: *progress,
                    message: message.to_string(),
                    error: None,
                },
            );
        }
    });

    Ok(id)
}

#[tauri::command]
fn cancel_contract_spike(
    app: AppHandle,
    id: String,
    state: State<'_, AppState>,
) -> Result<(), String> {
    if cancel_task_if_running(state.inner(), &id)? {
        emit_update(
            &app,
            TaskUpdate {
                protocol_version: 1,
                id,
                event: "status".to_string(),
                status: "CANCELLED".to_string(),
                stage: "cancelled".to_string(),
                progress: 0.0,
                message: "Task was cancelled by the user".to_string(),
                error: None,
            },
        );
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        bundled_sidecar_candidates, cancel_task_if_running, find_restored_artifact,
        finish_task_if_running, read_artifact_preview, resolve_controlled_path,
        validate_llm_settings, AppState, LlmConfigurationStatus, LlmSessionSettings, SidecarClient,
        TaskLifecycle, SIDECAR_EXECUTABLE_NAME,
    };

    #[test]
    fn task_lifecycle_keeps_cancellation_terminal() {
        let state = AppState::default();
        state
            .tasks
            .lock()
            .expect("task state should be writable")
            .insert("task-cancelled".to_string(), TaskLifecycle::Running);

        assert!(cancel_task_if_running(&state, "task-cancelled")
            .expect("running task should be cancellable"));
        assert!(!finish_task_if_running(&state, "task-cancelled"));
        assert!(!cancel_task_if_running(&state, "task-cancelled")
            .expect("cancelling twice should be an idempotent no-op"));
    }

    #[test]
    fn task_lifecycle_keeps_completion_terminal() {
        let state = AppState::default();
        state
            .tasks
            .lock()
            .expect("task state should be writable")
            .insert("task-completed".to_string(), TaskLifecycle::Running);

        assert!(finish_task_if_running(&state, "task-completed"));
        assert!(!cancel_task_if_running(&state, "task-completed")
            .expect("completed task cancellation should be an idempotent no-op"));
    }
    use serde_json::json;
    use std::{
        fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    #[test]
    fn llm_session_settings_are_validated_without_serializing_the_secret() {
        let (config, host) = validate_llm_settings(LlmSessionSettings {
            endpoint: "https://provider.example/v1/chat/completions".to_string(),
            model: "deployment-name".to_string(),
            api_key: "session-secret".to_string(),
            structured_output: "json_object".to_string(),
        })
        .expect("valid HTTPS settings should be accepted");
        assert_eq!(host, "provider.example");
        assert_eq!(
            config.endpoint,
            "https://provider.example/v1/chat/completions"
        );

        let status = LlmConfigurationStatus {
            configured: true,
            endpoint_host: Some(host),
            model: Some(config.model),
            input_reselection_required: true,
        };
        let serialized = serde_json::to_string(&status).expect("status should serialize");
        assert!(!serialized.contains("session-secret"));
        assert!(!serialized.contains("apiKey"));

        for endpoint in [
            "http://provider.example/v1/chat/completions",
            "https://user:pass@provider.example/v1/chat/completions",
            "https://provider.example/v1/chat/completions?debug=true",
        ] {
            assert!(validate_llm_settings(LlmSessionSettings {
                endpoint: endpoint.to_string(),
                model: "deployment-name".to_string(),
                api_key: "session-secret".to_string(),
                structured_output: "json_object".to_string(),
            })
            .is_err());
        }
        assert!(validate_llm_settings(LlmSessionSettings {
            endpoint: "https://provider.example/v1/chat/completions".to_string(),
            model: "deployment-name".to_string(),
            api_key: "secret with whitespace".to_string(),
            structured_output: "json_object".to_string(),
        })
        .is_err());
    }

    #[test]
    fn bundled_sidecar_candidates_cover_release_and_test_executables() {
        let extension = std::env::consts::EXE_EXTENSION;
        let sidecar_name = if extension.is_empty() {
            SIDECAR_EXECUTABLE_NAME.to_string()
        } else {
            format!("{SIDECAR_EXECUTABLE_NAME}.{extension}")
        };
        let release_dir = PathBuf::from("target").join("release");
        let release_executable = release_dir.join(if extension.is_empty() {
            "course-project-desktop".to_string()
        } else {
            format!("course-project-desktop.{extension}")
        });
        assert_eq!(
            bundled_sidecar_candidates(&release_executable),
            vec![release_dir.join(&sidecar_name)]
        );

        let test_executable = release_dir.join("deps").join("desktop-test");
        assert_eq!(
            bundled_sidecar_candidates(&test_executable),
            vec![
                release_dir.join("deps").join(&sidecar_name),
                release_dir.join(sidecar_name),
            ]
        );
    }

    #[test]
    fn controlled_restored_artifact_preview_enforces_task_manifest_and_root() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join(format!("course-project-restored-preview-{suffix}"));
        let artifact_dir = root.join("tasks").join("task-preview");
        fs::create_dir_all(&artifact_dir).expect("artifact directory should be writable");
        fs::write(artifact_dir.join("restored.json"), b"{\"ok\":true}\n")
            .expect("artifact should be writable");
        let root = root.canonicalize().expect("artifact root should resolve");
        let result = json!({
            "taskId": "task-preview",
            "artifacts": [{
                "artifactId": "restored-1",
                "type": "restored",
                "format": "json",
                "ref": "tasks/task-preview/restored.json"
            }, {
                "artifactId": "statistics-1",
                "type": "statistics",
                "format": "json",
                "ref": "tasks/task-preview/statistics.json"
            }]
        });
        let artifact = find_restored_artifact(&result, "restored-1")
            .expect("restored artifact should be present in the task manifest");
        let path = resolve_controlled_path(&root, &artifact.controlled_ref)
            .expect("controlled artifact should resolve beneath the root");
        let preview = read_artifact_preview(&artifact, &path, 64)
            .expect("bounded artifact preview should be readable");

        assert_eq!(preview.text.as_deref(), Some("{\"ok\":true}\n"));
        assert!(preview.eof);
        assert!(find_restored_artifact(&result, "statistics-1").is_err());
        assert!(resolve_controlled_path(&root, "../outside.bin").is_err());
        assert!(resolve_controlled_path(&root, "tasks\\task-preview\\restored.json").is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn sidecar_analyze_and_get_result_round_trip() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join(format!("course-project-sidecar-analyze-{suffix}"));
        fs::create_dir_all(&root).expect("temp state root should be writable");
        let sample = root.join("sample.dat");
        fs::write(&sample, b"header\0payload").expect("sample should be writable");

        let mut client = SidecarClient::spawn(None).expect("Python sidecar should start");
        let registered: serde_json::Value = client
            .request(
                "register_input",
                json!({"sourceRef": sample.to_string_lossy().replace('\\', "/")}),
            )
            .expect("register_input should return metadata");
        let input_ref = registered["inputRef"]
            .as_str()
            .expect("metadata should include inputRef")
            .to_string();
        let task_id = format!("desktop-test-{suffix}");
        let messages = client
            .request_messages_with_id(
                &task_id,
                "analyze",
                json!({
                    "inputRef": input_ref,
                    "mode": "baseline",
                    "stages": ["inspect", "features"],
                    "llmEnabled": false,
                    "verificationEnabled": true,
                    "behaviorEnabled": false,
                    "timeoutSeconds": 30,
                    "optionalDependencyPolicy": "degrade"
                }),
            )
            .expect("analyze should return task messages and a result ref");
        let result_ref = messages
            .iter()
            .find_map(|message| message.get("resultRef").and_then(|value| value.as_str()))
            .expect("analyze should return resultRef")
            .to_string();
        assert!(result_ref.starts_with("tasks/"));
        assert_eq!(
            client
                .request_result_ref(&task_id)
                .expect("get_result should return ref"),
            result_ref
        );
        let _ = fs::remove_dir_all(root);
        let state_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(std::path::Path::parent)
            .map(|path| {
                path.join(".course-project-state")
                    .join("tasks")
                    .join(task_id)
            });
        if let Some(state_root) = state_root {
            let _ = fs::remove_dir_all(state_root);
        }
    }

    #[test]
    fn sidecar_register_inspect_and_read_range_round_trip() {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("target")
            .join(format!("course-project-sidecar-{suffix}"));
        fs::create_dir_all(&root).expect("temp state root should be writable");
        let sample = root.join("sample.dat");
        fs::write(&sample, b"header\0payload").expect("sample should be writable");

        let mut client = SidecarClient::spawn(None).expect("Python sidecar should start");
        let registered: serde_json::Value = client
            .request(
                "register_input",
                json!({"sourceRef": sample.to_string_lossy().replace('\\', "/")}),
            )
            .expect("register_input should return metadata");
        let input_ref = registered
            .get("inputRef")
            .and_then(|value| value.as_str())
            .expect("metadata should include inputRef")
            .to_string();
        let inspected: serde_json::Value = client
            .request("inspect_file", json!({"inputRef": input_ref}))
            .expect("inspect_file should return metadata");
        assert_eq!(inspected["sizeBytes"], 14);
        let range: serde_json::Value = client
            .request(
                "read_range",
                json!({"inputRef": input_ref, "offset": 6, "length": 8}),
            )
            .expect("read_range should return bytes");
        assert_eq!(range["actualLength"], 8);
        assert_eq!(range["encoding"], "base64");
        let _ = fs::remove_dir_all(root);
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            start_contract_spike,
            configure_llm,
            get_analysis_result,
            read_restored_artifact,
            export_restored_artifact,
            review_export::export_review_json,
            cancel_contract_spike,
            select_input,
            inspect_file,
            read_range
        ])
        .run(tauri::generate_context!())
        .expect("error while running Evidence Workbench");
}
