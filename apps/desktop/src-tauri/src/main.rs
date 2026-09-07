use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    fs::File,
    io::{Read, Seek, SeekFrom},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};
use tauri::{AppHandle, Emitter, State};

const TASK_EVENT: &str = "task-update";

#[derive(Clone)]
struct AppState {
    tasks: Arc<Mutex<HashMap<String, bool>>>,
    inputs: Arc<Mutex<HashMap<String, RegisteredInput>>>,
    next_id: Arc<AtomicU64>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            tasks: Arc::new(Mutex::new(HashMap::new())),
            inputs: Arc::new(Mutex::new(HashMap::new())),
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

#[derive(Clone, Serialize)]
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

#[derive(Clone, Serialize)]
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

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct InputOverview {
    input_ref: String,
    size_bytes: u64,
    entropy: f64,
    printable_ratio: f64,
    distinct_byte_count: u64,
    zero_byte_ratio: f64,
    string_count: u64,
    longest_string: u64,
}

#[derive(Clone)]
struct RegisteredInput {
    metadata: InputMetadata,
    path: String,
}

fn emit_update(app: &AppHandle, update: TaskUpdate) {
    let _ = app.emit(TASK_EVENT, update);
}

#[tauri::command]
fn register_input(path: String, state: State<'_, AppState>) -> Result<InputMetadata, String> {
    let file_path = std::path::PathBuf::from(&path);
    let metadata =
        std::fs::metadata(&file_path).map_err(|error| format!("cannot read input: {error}"))?;
    if !metadata.is_file() {
        return Err("input path is not a regular file".to_string());
    }

    let mut file = File::open(&file_path).map_err(|error| format!("cannot open input: {error}"))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| format!("cannot hash input: {error}"))?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }

    let sha256 = format!("{:x}", hasher.finalize());
    let input_ref = format!("input-{}", &sha256[..16]);
    let kind = file_path
        .extension()
        .and_then(|value| value.to_str())
        .map(|value| match value.to_ascii_lowercase().as_str() {
            "dat" => "dat",
            "bin" => "bin",
            "pcap" => "pcap",
            "pcapng" => "pcapng",
            _ => "unknown",
        })
        .unwrap_or("unknown")
        .to_string();
    let result = InputMetadata {
        input_ref: input_ref.clone(),
        kind,
        size_bytes: metadata.len(),
        sha256,
        source_name: file_path
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("input")
            .to_string(),
        direction_available: false,
        timestamp_available: false,
    };

    state
        .inputs
        .lock()
        .map_err(|_| "input state is unavailable".to_string())?
        .insert(
            input_ref,
            RegisteredInput {
                metadata: result.clone(),
                path,
            },
        );
    Ok(result)
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
    let input = state
        .inputs
        .lock()
        .map_err(|_| "input state is unavailable".to_string())?
        .get(&input_ref)
        .cloned()
        .ok_or_else(|| "unknown inputRef".to_string())?;
    let mut file =
        File::open(&input.path).map_err(|error| format!("cannot open input: {error}"))?;
    file.seek(SeekFrom::Start(offset))
        .map_err(|error| format!("cannot seek input: {error}"))?;
    let mut bytes = vec![0_u8; length as usize];
    let actual = file
        .read(&mut bytes)
        .map_err(|error| format!("cannot read input range: {error}"))?;
    bytes.truncate(actual);
    Ok(RangeData {
        input_ref,
        offset,
        requested_length: length,
        actual_length: actual as u64,
        encoding: "base64".to_string(),
        bytes: BASE64.encode(bytes),
        eof: offset.saturating_add(actual as u64) >= input.metadata.size_bytes,
    })
}

#[tauri::command]
fn inspect_file(input_ref: String, state: State<'_, AppState>) -> Result<InputOverview, String> {
    let input = state
        .inputs
        .lock()
        .map_err(|_| "input state is unavailable".to_string())?
        .get(&input_ref)
        .cloned()
        .ok_or_else(|| "unknown inputRef".to_string())?;
    let mut file =
        File::open(&input.path).map_err(|error| format!("cannot open input: {error}"))?;
    let mut counts = [0_u64; 256];
    let mut total = 0_u64;
    let mut printable = 0_u64;
    let mut zeroes = 0_u64;
    let mut current_string = 0_u64;
    let mut string_count = 0_u64;
    let mut longest_string = 0_u64;
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| format!("cannot inspect input: {error}"))?;
        if count == 0 {
            break;
        }
        for &byte in &buffer[..count] {
            counts[byte as usize] += 1;
            total += 1;
            if byte == 0 {
                zeroes += 1;
            }
            if byte.is_ascii_graphic() || byte == b' ' {
                printable += 1;
                current_string += 1;
            } else if current_string >= 4 {
                string_count += 1;
                longest_string = longest_string.max(current_string);
                current_string = 0;
            } else {
                current_string = 0;
            }
        }
    }
    if current_string >= 4 {
        string_count += 1;
        longest_string = longest_string.max(current_string);
    }
    let entropy = if total == 0 {
        0.0
    } else {
        counts
            .iter()
            .filter(|&&count| count > 0)
            .map(|&count| {
                let probability = count as f64 / total as f64;
                -probability * probability.log2()
            })
            .sum()
    };
    Ok(InputOverview {
        input_ref,
        size_bytes: total,
        entropy,
        printable_ratio: if total == 0 {
            0.0
        } else {
            printable as f64 / total as f64
        },
        distinct_byte_count: counts.iter().filter(|&&count| count > 0).count() as u64,
        zero_byte_ratio: if total == 0 {
            0.0
        } else {
            zeroes as f64 / total as f64
        },
        string_count,
        longest_string,
    })
}

#[tauri::command]
fn start_contract_spike(
    app: AppHandle,
    state: State<'_, AppState>,
    failure_mode: bool,
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

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            start_contract_spike,
            cancel_contract_spike,
            register_input,
            read_range,
            inspect_file
        ])
        .run(tauri::generate_context!())
        .expect("error while running Evidence Workbench");
}
