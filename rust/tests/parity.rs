/// Parity test harness for Python vs Rust i4z-terminal-mcp implementations.
///
/// These tests compare HTTP API responses between the two implementations.
/// Run with: `cargo test --test parity -- --nocapture`
///
/// The Python server must be running on port 19020:
///   I4Z_TERMINAL_WEB_PORT=19020 I4Z_TERMINAL_STATE_DIR=/tmp/i4z-test-py i4z-terminal-mcp
///
/// The Rust server runs on port 19021 (started automatically or manually):
///   I4Z_TERMINAL_WEB_PORT=19021 cargo run

use std::process::{Command, Child};
use std::time::Duration;
use std::collections::HashMap;

const PY_URL: &str = "http://127.0.0.1:19020";
const RS_URL: &str = "http://127.0.0.1:19021";

async fn get_json(url: &str) -> Result<serde_json::Value, reqwest::Error> {
    let client = reqwest::Client::new();
    client.get(url).send().await?.json().await
}

async fn post_json(url: &str, body: &serde_json::Value) -> Result<serde_json::Value, reqwest::Error> {
    let client = reqwest::Client::new();
    client.post(url).json(body).send().await?.json().await
}

async fn delete_json(url: &str) -> Result<serde_json::Value, reqwest::Error> {
    let client = reqwest::Client::new();
    client.delete(url).send().await?.json().await
}

struct Diff {
    endpoint: String,
    field: String,
    py_value: String,
    rs_value: String,
}

async fn compare_endpoint(
    endpoint: &str,
    method: &str,
    body: Option<&serde_json::Value>,
) -> Vec<Diff> {
    let py_url = format!("{PY_URL}{endpoint}");
    let rs_url = format!("{RS_URL}{endpoint}");

    let py_resp: Result<serde_json::Value, _> = match method {
        "GET" => get_json(&py_url).await,
        "POST" => post_json(&py_url, body.unwrap_or(&serde_json::json!({}))).await,
        "DELETE" => delete_json(&py_url).await,
        _ => unreachable!(),
    };

    let rs_resp: Result<serde_json::Value, _> = match method {
        "GET" => get_json(&rs_url).await,
        "POST" => post_json(&rs_url, body.unwrap_or(&serde_json::json!({}))).await,
        "DELETE" => delete_json(&rs_url).await,
        _ => unreachable!(),
    };

    let py = py_resp.unwrap_or(serde_json::json!({}));
    let rs = rs_resp.unwrap_or(serde_json::json!({}));

    diff_values(endpoint, "", &py, &rs, &mut Vec::new())
}

fn diff_values(
    endpoint: &str,
    path: &str,
    py: &serde_json::Value,
    rs: &serde_json::Value,
    diffs: &mut Vec<Diff>,
) -> Vec<Diff> {
    // Skip comparing server-generated values
    let skip_paths = [
        "pid", "cwd", "created_at", "last_activity", "timestamp", "ts",
        "reader_error", "updated_at", "db.path", "exported_at",
        "cursor",  // cursors differ because terminal output includes different boot messages
    ];

    let full_path = if path.is_empty() { endpoint.to_string() } else { format!("{endpoint}.{path}") };

    for skip in &skip_paths {
        if path.ends_with(skip) {
            return vec![];
        }
    }

    match (py, rs) {
        (serde_json::Value::Object(py_map), serde_json::Value::Object(rs_map)) => {
            let mut result = Vec::new();
            let mut all_keys: Vec<&String> = py_map.keys().collect();
            all_keys.extend(rs_map.keys());
            all_keys.sort();
            all_keys.dedup();

            for key in all_keys {
                let py_val = py_map.get(key);
                let rs_val = rs_map.get(key);
                let child_path = if path.is_empty() { key.clone() } else { format!("{path}.{key}") };

                match (py_val, rs_val) {
                    (Some(pv), Some(rv)) => {
                        if pv.is_object() && rv.is_object() {
                            diff_values(endpoint, &child_path, pv, rv, &mut result);
                        } else if pv.is_array() && rv.is_array() {
                            // For arrays, just compare lengths and element types
                            let py_arr = pv.as_array().unwrap();
                            let rs_arr = rv.as_array().unwrap();
                            if py_arr.len() != rs_arr.len() {
                                result.push(Diff {
                                    endpoint: endpoint.to_string(),
                                    field: format!("{child_path}.length"),
                                    py_value: format!("{}", py_arr.len()),
                                    rs_value: format!("{}", rs_arr.len()),
                                });
                            }
                        } else if !values_equivalent(pv, rv) {
                            result.push(Diff {
                                endpoint: endpoint.to_string(),
                                field: child_path,
                                py_value: format!("{:?}", pv),
                                rs_value: format!("{:?}", rv),
                            });
                        }
                    }
                    (Some(pv), None) => {
                        result.push(Diff {
                            endpoint: endpoint.to_string(),
                            field: child_path,
                            py_value: format!("{:?}", pv),
                            rs_value: "missing".into(),
                        });
                    }
                    (None, Some(rv)) => {
                        result.push(Diff {
                            endpoint: endpoint.to_string(),
                            field: child_path,
                            py_value: "missing".into(),
                            rs_value: format!("{:?}", rv),
                        });
                    }
                    (None, None) => {}
                }
            }
            result
        }
        _ => {
            if !values_equivalent(py, rs) {
                vec![Diff {
                    endpoint: endpoint.to_string(),
                    field: path.to_string(),
                    py_value: format!("{:?}", py),
                    rs_value: format!("{:?}", rs),
                }]
            } else {
                vec![]
            }
        }
    }
}

fn values_equivalent(py: &serde_json::Value, rs: &serde_json::Value) -> bool {
    match (py, rs) {
        (serde_json::Value::String(p), serde_json::Value::String(r)) => p == r,
        (serde_json::Value::Number(p), serde_json::Value::Number(r)) => p == r,
        (serde_json::Value::Bool(p), serde_json::Value::Bool(r)) => p == r,
        (serde_json::Value::Null, serde_json::Value::Null) => true,
        // Numbers vs bools: coerce if one is integer 0/1 and other is false/true
        (serde_json::Value::Number(n), serde_json::Value::Bool(b)) => {
            if let Some(i) = n.as_i64() {
                (i == 0 && !b) || (i == 1 && *b) || (i > 0 && *b)
            } else {
                false
            }
        }
        (serde_json::Value::Bool(b), serde_json::Value::Number(n)) => {
            if let Some(i) = n.as_i64() {
                (*b && i == 1) || (!*b && i == 0) || (*b && i > 0)
            } else {
                false
            }
        }
        _ => false,
    }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_health() {
    let diffs = compare_endpoint("/api/health", "GET", None).await;
    if !diffs.is_empty() {
        eprintln!("\n=== Health endpoint diffs ===");
        for d in &diffs {
            eprintln!("  {}: Python={}, Rust={}", d.field, d.py_value, d.rs_value);
        }
    }
    // Health should work even without terminals
    assert!(diffs.iter().filter(|d| d.field.contains("db.ok")).count() == 0, "db.ok should match");
}

#[tokio::test]
async fn test_terminals_list() {
    let diffs = compare_endpoint("/api/terminals", "GET", None).await;
    if !diffs.is_empty() {
        eprintln!("\n=== Terminals list diffs ===");
        for d in &diffs {
            eprintln!("  {}: Python={}, Rust={}", d.field, d.py_value, d.rs_value);
        }
    }
}

#[tokio::test]
async fn test_create_and_lifecycle() {
    let name = format!("parity-test-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    // Create terminal
    let create_body = serde_json::json!({ "name": name.clone() });

    let py_create = post_json(&format!("{PY_URL}/api/create"), &create_body).await.unwrap();
    let rs_create = post_json(&format!("{RS_URL}/api/create"), &create_body).await.unwrap();

    // Give terminals time to initialize
    tokio::time::sleep(Duration::from_millis(200)).await;

    // Check create response shape
    assert!(py_create.get("terminal_id").is_some(), "Python create missing terminal_id");
    assert!(rs_create.get("terminal_id").is_some(), "Rust create missing terminal_id");
    assert_eq!(py_create.get("status"), rs_create.get("status"));

    // Send commands
    let send_body = serde_json::json!({ "text": "echo 'parity test'\n" });
    post_json(&format!("{PY_URL}/api/send/{name}"), &send_body).await.unwrap();
    post_json(&format!("{RS_URL}/api/send/{name}"), &send_body).await.unwrap();

    tokio::time::sleep(Duration::from_millis(300)).await;

    // Read output
    let py_output = get_json(&format!("{PY_URL}/api/output/{name}?since=0")).await.unwrap();
    let rs_output = get_json(&format!("{RS_URL}/api/output/{name}?since=0")).await.unwrap();

    // Both should have output and cursor
    assert!(py_output.get("output").is_some(), "Python read_output missing output field");
    assert!(rs_output.get("output").is_some(), "Rust read_output missing output field");
    assert!(py_output.get("cursor").is_some(), "Python read_output missing cursor field");
    assert!(rs_output.get("cursor").is_some(), "Rust read_output missing cursor field");

    // Get status
    let py_status = get_json(&format!("{PY_URL}/api/status/{name}")).await.unwrap();
    let rs_status = get_json(&format!("{RS_URL}/api/status/{name}")).await.unwrap();

    assert!(py_status.get("alive").and_then(|v| v.as_bool()).unwrap_or(false), "Python terminal not alive");
    assert!(rs_status.get("alive").and_then(|v| v.as_bool()).unwrap_or(false), "Rust terminal not alive");

    // Kill
    let _ = post_json(&format!("{PY_URL}/api/kill/{name}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{name}"), &serde_json::json!({})).await;

    eprintln!("  create/lifecycle test passed: Python={:?}, Rust={:?}",
        py_create.get("terminal_id"), rs_create.get("terminal_id"));
}

#[tokio::test]
async fn test_profile_operations() {
    let name = format!("prof-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    let create_body = serde_json::json!({ "name": name.clone() });
    let _ = post_json(&format!("{PY_URL}/api/create"), &create_body).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/create"), &create_body).await.unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;

    // Get profile
    let py_prof = get_json(&format!("{PY_URL}/api/profile/{name}")).await.unwrap();
    let rs_prof = get_json(&format!("{RS_URL}/api/profile/{name}")).await.unwrap();

    assert!(py_prof.get("env").is_some(), "Python profile missing env");
    assert!(rs_prof.get("env").is_some(), "Rust profile missing env");

    // Set env
    let prof_body = serde_json::json!({ "set_env": { "PARITY_TEST": "hello" } });
    post_json(&format!("{PY_URL}/api/profile/{name}"), &prof_body).await.unwrap();
    post_json(&format!("{RS_URL}/api/profile/{name}"), &prof_body).await.unwrap();

    let py_prof2 = get_json(&format!("{PY_URL}/api/profile/{name}")).await.unwrap();
    let rs_prof2 = get_json(&format!("{RS_URL}/api/profile/{name}")).await.unwrap();

    eprintln!("  Profile test: Python env={:?}, Rust env={:?}",
        py_prof2.get("env"), rs_prof2.get("env"));

    // Cleanup
    let _ = post_json(&format!("{PY_URL}/api/kill/{name}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{name}"), &serde_json::json!({})).await;
}

#[tokio::test]
async fn test_workspace_operations() {
    let ws_id = format!("ws-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());
    let tid = format!("ws-term-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    // Create workspace
    let ws_body = serde_json::json!({
        "workspace_id": ws_id.clone(),
        "env": { "WS_VAR": "val" },
        "startup_commands": ["echo 'ws init'"]
    });
    let _ = post_json(&format!("{PY_URL}/api/workspaces"), &ws_body).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/workspaces"), &ws_body).await.unwrap();

    // Create terminal with workspace
    let create_body = serde_json::json!({ "name": tid.clone(), "workspace_id": ws_id.clone() });
    let _ = post_json(&format!("{PY_URL}/api/create"), &create_body).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/create"), &create_body).await.unwrap();
    tokio::time::sleep(Duration::from_millis(300)).await;

    // Check workspace members
    let py_ws = get_json(&format!("{PY_URL}/api/workspaces/{ws_id}")).await.unwrap();
    let rs_ws = get_json(&format!("{RS_URL}/api/workspaces/{ws_id}")).await.unwrap();

    eprintln!("  Workspace test: Python members={:?}, Rust members={:?}",
        py_ws.get("members"), rs_ws.get("members"));

    // Cleanup
    let _ = post_json(&format!("{PY_URL}/api/kill/{tid}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{tid}"), &serde_json::json!({})).await;
}

#[tokio::test]
async fn test_alerts() {
    let name = format!("alert-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    let _ = post_json(&format!("{PY_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;

    // Add alert
    let alert_body = serde_json::json!({
        "scope": "session",
        "pattern": "alert_test",
        "terminal_id": name.clone(),
        "label": "test-alert"
    });
    let py_alert = post_json(&format!("{PY_URL}/api/alerts"), &alert_body).await.unwrap();
    let rs_alert = post_json(&format!("{RS_URL}/api/alerts"), &alert_body).await.unwrap();

    assert!(py_alert.get("id").is_some(), "Python alert missing id");
    assert!(rs_alert.get("id").is_some(), "Rust alert missing id");

    // Trigger alert
    let send_body = serde_json::json!({ "text": "echo 'alert_test triggered'\n" });
    post_json(&format!("{PY_URL}/api/send/{name}"), &send_body).await.unwrap();
    post_json(&format!("{RS_URL}/api/send/{name}"), &send_body).await.unwrap();
    tokio::time::sleep(Duration::from_millis(300)).await;

    // Check alert events
    let py_events = get_json(&format!("{PY_URL}/api/alert-events?terminal_id={name}")).await.unwrap();
    let rs_events = get_json(&format!("{RS_URL}/api/alert-events?terminal_id={name}")).await.unwrap();

    eprintln!("  Alert test: Python events={:?}, Rust events={:?}", py_events, rs_events);

    // Cleanup
    let _ = post_json(&format!("{PY_URL}/api/kill/{name}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{name}"), &serde_json::json!({})).await;
}

#[tokio::test]
async fn test_wait_for_output() {
    let name = format!("wait-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    let _ = post_json(&format!("{PY_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;

    // Send command and wait for output concurrently
    let py_name = name.clone();
    let rs_name = name.clone();

    let py_handle = tokio::spawn(async move {
        // We need to check if the wait API exists on both
        // Python: wait_for_output tool, not a direct REST endpoint easily
        // Instead, check output for the pattern
        let send_body = serde_json::json!({ "text": "echo 'wait-target'\n" });
        let _ = post_json(&format!("{PY_URL}/api/send/{py_name}"), &send_body).await.unwrap();
        tokio::time::sleep(Duration::from_millis(500)).await;
        get_json(&format!("{PY_URL}/api/search/{py_name}?query=wait-target")).await.unwrap()
    });

    let rs_handle = tokio::spawn(async move {
        let send_body = serde_json::json!({ "text": "echo 'wait-target'\n" });
        let _ = post_json(&format!("{RS_URL}/api/send/{rs_name}"), &send_body).await.unwrap();
        tokio::time::sleep(Duration::from_millis(500)).await;
        get_json(&format!("{RS_URL}/api/search/{rs_name}?query=wait-target")).await.unwrap()
    });

    let (py_search, rs_search) = tokio::join!(py_handle, rs_handle);
    let py_search = py_search.unwrap();
    let rs_search = rs_search.unwrap();

    eprintln!("  Wait/search test: Python search={:?}, Rust search={:?}", py_search, rs_search);

    assert!(py_search.get("matches").is_some(), "Python search missing matches");
    assert!(rs_search.get("matches").is_some(), "Rust search missing matches");

    // Cleanup
    let _ = post_json(&format!("{PY_URL}/api/kill/{name}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{name}"), &serde_json::json!({})).await;
}

#[tokio::test]
async fn test_concurrent_sessions() {
    let mut names = Vec::new();
    for i in 0..3 {
        let name = format!("conc-{}-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap(), i);
        names.push(name.clone());
        let body = serde_json::json!({ "name": name.clone() });
        let _ = post_json(&format!("{PY_URL}/api/create"), &body).await.unwrap();
        let _ = post_json(&format!("{RS_URL}/api/create"), &body).await.unwrap();
    }
    tokio::time::sleep(Duration::from_millis(300)).await;

    // List both
    let py_terms = get_json(&format!("{PY_URL}/api/terminals")).await.unwrap();
    let rs_terms = get_json(&format!("{RS_URL}/api/terminals")).await.unwrap();

    let py_count = py_terms.as_array().map(|a| a.len()).unwrap_or(0);
    let rs_count = rs_terms.as_array().map(|a| a.len()).unwrap_or(0);
    eprintln!("  Concurrent test: Python={} terminals, Rust={} terminals", py_count, rs_count);
    assert!(py_count >= 3, "Python should have >= 3 terminals, got {}", py_count);
    assert!(rs_count >= 3, "Rust should have >= 3 terminals, got {}", rs_count);

    // Cleanup
    for name in &names {
        let _ = post_json(&format!("{PY_URL}/api/kill/{name}"), &serde_json::json!({})).await;
        let _ = post_json(&format!("{RS_URL}/api/kill/{name}"), &serde_json::json!({})).await;
    }
}

#[tokio::test]
async fn test_rename() {
    let name = format!("rename-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());
    let new_name = format!("renamed-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    let _ = post_json(&format!("{PY_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;

    let py_rename = post_json(&format!("{PY_URL}/api/rename/{name}"), &serde_json::json!({ "new_id": new_name.clone() })).await.unwrap();
    let rs_rename = post_json(&format!("{RS_URL}/api/rename/{name}"), &serde_json::json!({ "new_id": new_name.clone() })).await.unwrap();

    eprintln!("  Rename test: Python={:?}, Rust={:?}", py_rename, rs_rename);

    // Cleanup (use new name)
    let _ = post_json(&format!("{PY_URL}/api/kill/{new_name}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{new_name}"), &serde_json::json!({})).await;
}

#[tokio::test]
async fn test_checkpoints() {
    let name = format!("cp-{}", uuid::Uuid::new_v4().to_string().split('-').next().unwrap());

    let _ = post_json(&format!("{PY_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    let _ = post_json(&format!("{RS_URL}/api/create"), &serde_json::json!({ "name": name.clone() })).await.unwrap();
    tokio::time::sleep(Duration::from_millis(200)).await;

    let cp_body = serde_json::json!({
        "terminal_id": name.clone(),
        "label": "test-checkpoint",
        "note": "parity-test"
    });
    let py_cp = post_json(&format!("{PY_URL}/api/checkpoints"), &cp_body).await.unwrap();
    let rs_cp = post_json(&format!("{RS_URL}/api/checkpoints"), &cp_body).await.unwrap();

    eprintln!("  Checkpoint test: Python={:?}, Rust={:?}", py_cp, rs_cp);

    assert!(py_cp.get("id").is_some(), "Python checkpoint missing id");
    assert!(rs_cp.get("id").is_some(), "Rust checkpoint missing id");

    // List checkpoints
    let py_list = get_json(&format!("{PY_URL}/api/checkpoints?terminal_id={name}")).await.unwrap();
    let rs_list = get_json(&format!("{RS_URL}/api/checkpoints?terminal_id={name}")).await.unwrap();

    eprintln!("  Checkpoint list: Python={:?}, Rust={:?}", py_list, rs_list);

    // Cleanup
    let _ = post_json(&format!("{PY_URL}/api/kill/{name}"), &serde_json::json!({})).await;
    let _ = post_json(&format!("{RS_URL}/api/kill/{name}"), &serde_json::json!({})).await;
}
