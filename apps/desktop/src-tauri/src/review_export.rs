use serde_json::Value;
use std::{fs, path::Path};
use tauri::AppHandle;
use tauri_plugin_dialog::DialogExt;

const MAX_REVIEW_EXPORT_BYTES: usize = 4 * 1024 * 1024;

fn prepare_review_export(payload: &Value, suggested_name: &str) -> Result<(String, Vec<u8>), String> {
    if !payload.is_object() {
        return Err("review export payload must be a JSON object".to_string());
    }

    let name = suggested_name.trim();
    let safe_name = !name.is_empty()
        && name.len() <= 240
        && name.ends_with(".json")
        && !name.contains('/')
        && !name.contains('\\')
        && !name.chars().any(char::is_control)
        && Path::new(name).file_name().and_then(|value| value.to_str()) == Some(name);
    if !safe_name {
        return Err("suggested review export name must be a safe .json file name".to_string());
    }

    let mut bytes = serde_json::to_vec_pretty(payload)
        .map_err(|error| format!("cannot encode review export JSON: {error}"))?;
    bytes.push(b'\n');
    if bytes.len() > MAX_REVIEW_EXPORT_BYTES {
        return Err(format!(
            "review export exceeds the {MAX_REVIEW_EXPORT_BYTES}-byte safety limit"
        ));
    }
    Ok((name.to_string(), bytes))
}

#[tauri::command]
pub async fn export_review_json(
    app: AppHandle,
    payload: Value,
    suggested_name: String,
) -> Result<Option<String>, String> {
    let (default_name, bytes) = prepare_review_export(&payload, &suggested_name)?;
    let (sender, receiver) = std::sync::mpsc::channel();
    app.dialog()
        .file()
        .add_filter("Review JSON", &["json"])
        .set_title("Export review JSON")
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
        .map_err(|error| format!("cannot access review export destination: {error:?}"))?;
    fs::write(&destination, bytes)
        .map_err(|error| format!("cannot export review JSON: {error}"))?;
    let exported_name = destination
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("review.json")
        .to_string();
    Ok(Some(exported_name))
}

#[cfg(test)]
mod tests {
    use super::prepare_review_export;
    use serde_json::json;

    #[test]
    fn review_export_serializes_pretty_json_with_terminal_newline() {
        let payload = json!({
            "protocolVersion": 1,
            "taskId": "task-1",
            "reviews": [{"findingId": "f-1", "review": "accepted"}]
        });
        let (name, bytes) = prepare_review_export(&payload, "task-1-review.json")
            .expect("valid review export should be prepared");
        assert_eq!(name, "task-1-review.json");
        assert_eq!(bytes.last(), Some(&b'\n'));
        let decoded: serde_json::Value = serde_json::from_slice(&bytes)
            .expect("prepared bytes should remain valid JSON");
        assert_eq!(decoded, payload);
    }

    #[test]
    fn review_export_rejects_unsafe_names_and_non_object_payloads() {
        let payload = json!({"protocolVersion": 1});
        for name in ["", "../review.json", "folder/review.json", "folder\\review.json", "review.txt"] {
            assert!(prepare_review_export(&payload, name).is_err(), "unsafe name should fail: {name}");
        }
        assert!(prepare_review_export(&json!([1, 2, 3]), "review.json").is_err());
    }
}
