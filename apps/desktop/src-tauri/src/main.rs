use serde::Serialize;
use std::{
    collections::HashMap,
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
    next_id: Arc<AtomicU64>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            tasks: Arc::new(Mutex::new(HashMap::new())),
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

fn emit_update(app: &AppHandle, update: TaskUpdate) {
    let _ = app.emit(TASK_EVENT, update);
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
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            start_contract_spike,
            cancel_contract_spike
        ])
        .run(tauri::generate_context!())
        .expect("error while running Evidence Workbench");
}
