use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    fs,
    io::{BufRead, BufReader, Write},
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

#[derive(Clone)]
struct AppState {
    tasks: Arc<Mutex<HashMap<String, bool>>>,
    sidecar: Arc<Mutex<Option<SidecarClient>>>,
    next_id: Arc<AtomicU64>,
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

struct SidecarClient {
    _child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
    next_id: u64,
}

impl Drop for SidecarClient {
    fn drop(&mut self) {
        let _ = self._child.kill();
        let _ = self._child.wait();
    }
}

impl SidecarClient {
    fn spawn() -> Result<Self, String> {
        let program = std::env::var("COURSE_PROJECT_SIDECAR_COMMAND")
            .unwrap_or_else(|_| "python".to_string());
        let state_dir = std::env::var("COURSE_PROJECT_STATE_DIR")
            .unwrap_or_else(|_| ".course-project-state".to_string());
        let mut command = Command::new(program);
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
        let mut child = command
            .args(["-m", "course_project.sidecar", "--state-dir", &state_dir])
            .env("PYTHONPATH", python_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .spawn()
            .map_err(|error| format!("cannot start Python sidecar: {error}"))?;
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
    state: &State<'_, AppState>,
    method: &str,
    params: Value,
) -> Result<T, String> {
    let mut guard = state
        .sidecar
        .lock()
        .map_err(|_| "sidecar state is unavailable".to_string())?;
    if guard.is_none() {
        *guard = Some(SidecarClient::spawn()?);
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
    sidecar_request(
        &state,
        "register_input",
        json!({"sourceRef": path.to_string_lossy().replace('\\', "/")}),
    )
    .map(Some)
}

#[tauri::command]
fn inspect_file(input_ref: String, state: State<'_, AppState>) -> Result<InputMetadata, String> {
    sidecar_request(&state, "inspect_file", json!({"inputRef": input_ref}))
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
        &state,
        "read_range",
        json!({"inputRef": input_ref, "offset": offset, "length": length}),
    )
}

fn emit_update(app: &AppHandle, update: TaskUpdate) {
    let _ = app.emit(TASK_EVENT, update);
}

fn result_state_root() -> Result<PathBuf, String> {
    let configured = std::env::var("COURSE_PROJECT_STATE_DIR")
        .unwrap_or_else(|_| ".course-project-state".to_string());
    let path = PathBuf::from(configured);
    let absolute = if path.is_absolute() {
        path
    } else {
        std::env::current_dir()
            .map_err(|error| format!("cannot resolve sidecar state directory: {error}"))?
            .join(path)
    };
    absolute
        .canonicalize()
        .map_err(|error| format!("cannot access sidecar state directory: {error}"))
}

fn read_controlled_result(result_ref: &str) -> Result<Value, String> {
    let relative = Path::new(result_ref);
    if result_ref.is_empty()
        || relative.is_absolute()
        || relative
            .components()
            .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("sidecar returned an unsafe result reference".to_string());
    }
    let root = result_state_root()?;
    let target = root
        .join(relative)
        .canonicalize()
        .map_err(|error| format!("cannot read controlled analysis result: {error}"))?;
    if !target.starts_with(&root) {
        return Err("sidecar result escapes the controlled state directory".to_string());
    }
    let content = fs::read_to_string(target)
        .map_err(|error| format!("cannot read controlled analysis result: {error}"))?;
    serde_json::from_str(&content).map_err(|error| format!("invalid analysis result JSON: {error}"))
}

fn run_sidecar_analysis(
    app: &AppHandle,
    state: &AppState,
    task_id: &str,
    input_ref: &str,
) -> Result<(), String> {
    let params = json!({
        "inputRef": input_ref,
        "mode": "baseline",
        "stages": ["inspect", "features", "boundary", "inference", "evidence", "verification", "behavior"],
        "llmEnabled": false,
        "verificationEnabled": true,
        "behaviorEnabled": true,
        "timeoutSeconds": 300,
        "optionalDependencyPolicy": "degrade"
    });
    let messages = {
        let mut guard = state
            .sidecar
            .lock()
            .map_err(|_| "sidecar state is unavailable".to_string())?;
        if guard.is_none() {
            *guard = Some(SidecarClient::spawn()?);
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
    for message in messages {
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
    let result_ref = {
        let mut guard = state
            .sidecar
            .lock()
            .map_err(|_| "sidecar state is unavailable".to_string())?;
        if guard.is_none() {
            *guard = Some(SidecarClient::spawn()?);
        }
        let result = guard
            .as_mut()
            .expect("sidecar initialized")
            .request_result_ref(&task_id);
        if result.is_err() {
            *guard = None;
        }
        result?
    };
    read_controlled_result(&result_ref)
}

#[tauri::command]
fn start_contract_spike(
    app: AppHandle,
    state: State<'_, AppState>,
    failure_mode: bool,
    input_ref: Option<String>,
) -> Result<String, String> {
    let id = format!("contract-{}", state.next_id.fetch_add(1, Ordering::SeqCst));
    state
        .tasks
        .lock()
        .map_err(|_| "task state is unavailable".to_string())?
        .insert(id.clone(), false);

    let task_state = state.inner().clone();
    let task_id = id.clone();
    tauri::async_runtime::spawn(async move {
        if let Some(input_ref) = input_ref {
            if let Err(error) = run_sidecar_analysis(&app, &task_state, &task_id, &input_ref) {
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
            let cancelled = task_state
                .tasks
                .lock()
                .map(|tasks| tasks.get(&task_id).copied().unwrap_or(false))
                .unwrap_or(true);
            if cancelled {
                emit_update(
                    &app,
                    TaskUpdate {
                        protocol_version: 1,
                        id: task_id.clone(),
                        event: "status".to_string(),
                        status: "CANCELLED".to_string(),
                        stage: "cancelled".to_string(),
                        progress: *progress,
                        message: "Task was cancelled by the user".to_string(),
                        error: None,
                    },
                );
                return;
            }

            if failure_mode && index == 2 {
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
fn cancel_contract_spike(id: String, state: State<'_, AppState>) -> Result<(), String> {
    let mut tasks = state
        .tasks
        .lock()
        .map_err(|_| "task state is unavailable".to_string())?;
    let task = tasks
        .get_mut(&id)
        .ok_or_else(|| format!("unknown task: {id}"))?;
    *task = true;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::SidecarClient;
    use serde_json::json;
    use std::{
        fs,
        time::{SystemTime, UNIX_EPOCH},
    };

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

        let mut client = SidecarClient::spawn().expect("Python sidecar should start");
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

        let mut client = SidecarClient::spawn().expect("Python sidecar should start");
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
            get_analysis_result,
            cancel_contract_spike,
            select_input,
            inspect_file,
            read_range
        ])
        .run(tauri::generate_context!())
        .expect("error while running Evidence Workbench");
}
