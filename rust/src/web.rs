use std::sync::Arc;

use actix_cors::Cors;
use actix_web::{web, App, HttpRequest, HttpResponse, HttpServer, Responder};
use actix_ws::Message;
use serde::Deserialize;
use serde_json::Value;
use tokio::sync::broadcast;

use crate::manager::Manager;

const HTML: &str = include_str!("../index.html");

type Data = web::Data<Arc<Manager>>;

// ── helpers ───────────────────────────────────────────────────────────────────

fn ok(v: impl serde::Serialize) -> HttpResponse {
    HttpResponse::Ok().json(v)
}

fn err(msg: impl std::fmt::Display) -> HttpResponse {
    HttpResponse::BadRequest().json(serde_json::json!({ "error": msg.to_string() }))
}

fn not_found(msg: impl std::fmt::Display) -> HttpResponse {
    HttpResponse::NotFound().json(serde_json::json!({ "error": msg.to_string() }))
}

// ── routes ────────────────────────────────────────────────────────────────────

async fn index() -> impl Responder {
    HttpResponse::Ok().content_type("text/html; charset=utf-8").body(HTML)
}

async fn api_health(mgr: Data) -> impl Responder {
    match mgr.health().await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_info(mgr: Data) -> impl Responder {
    let web_url = mgr.web_url.read().await.clone();
    ok(serde_json::json!({
        "name": "i4z-terminal-mcp",
        "version": env!("CARGO_PKG_VERSION"),
        "implementation": "rust",
        "web_url": web_url,
    }))
}

async fn api_terminals(mgr: Data) -> impl Responder {
    ok(mgr.list_all().await)
}

#[derive(Deserialize)]
struct CreateBody {
    name: String,
    #[serde(default)]
    env: Option<std::collections::HashMap<String, String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
    #[serde(default)]
    workspace_id: Option<String>,
    #[serde(default)]
    interactive: Option<bool>,
    #[serde(default)]
    run_startup_commands: Option<bool>,
}

async fn api_create(mgr: Data, body: web::Json<CreateBody>) -> impl Responder {
    match mgr
        .create(
            &body.name,
            body.env.clone(),
            body.startup_commands.clone(),
            body.workspace_id.as_deref(),
            body.interactive.unwrap_or(false),
            body.run_startup_commands.unwrap_or(true),
        )
        .await
    {
        Ok(s) => ok(serde_json::json!({ "terminal_id": s.id, "status": "created" })),
        Err(e) => err(e),
    }
}

async fn api_status(mgr: Data, path: web::Path<String>) -> impl Responder {
    let id = path.into_inner();
    match mgr.status(&id).await {
        Ok(v) => ok(v),
        Err(e) => not_found(e),
    }
}

async fn api_profile_get(mgr: Data, path: web::Path<String>) -> impl Responder {
    let id = path.into_inner();
    match mgr.get_profile(&id).await {
        Ok(v) => ok(v),
        Err(_) => ok(serde_json::json!({ "env": {}, "startup_commands": [] })),
    }
}

#[derive(Deserialize)]
struct ProfileBody {
    #[serde(default)]
    set_env: Option<std::collections::HashMap<String, String>>,
    #[serde(default)]
    unset_env: Option<Vec<String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
    #[serde(default)]
    run_startup_commands: Option<bool>,
}

async fn api_profile_update(
    mgr: Data,
    path: web::Path<String>,
    body: web::Json<ProfileBody>,
) -> impl Responder {
    let id = path.into_inner();
    match mgr
        .configure_terminal(
            &id,
            body.set_env.clone(),
            body.unset_env.clone(),
            body.startup_commands.clone(),
            body.run_startup_commands.unwrap_or(false),
        )
        .await
    {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_kill(mgr: Data, path: web::Path<String>) -> impl Responder {
    let id = path.into_inner();
    match mgr.kill(&id).await {
        Ok(_) => ok(serde_json::json!({ "status": "killed" })),
        Err(e) => err(e),
    }
}

async fn api_delete_terminal(mgr: Data, path: web::Path<String>) -> impl Responder {
    let id = path.into_inner();
    match mgr.delete_terminal(&id).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct RenameBody {
    new_id: String,
}

async fn api_rename(mgr: Data, path: web::Path<String>, body: web::Json<RenameBody>) -> impl Responder {
    match mgr.rename(&path.into_inner(), &body.new_id).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct ResizeBody {
    rows: u16,
    cols: u16,
}

async fn api_resize(mgr: Data, path: web::Path<String>, body: web::Json<ResizeBody>) -> impl Responder {
    match mgr.resize(&path.into_inner(), body.rows, body.cols) {
        Ok(_) => ok(serde_json::json!({ "status": "resized" })),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct SignalBody {
    signal: String,
}

async fn api_signal(mgr: Data, path: web::Path<String>, body: web::Json<SignalBody>) -> impl Responder {
    match mgr.signal(&path.into_inner(), &body.signal).await {
        Ok(_) => ok(serde_json::json!({ "status": "signaled" })),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct SendBody {
    text: String,
}

async fn api_send(mgr: Data, path: web::Path<String>, body: web::Json<SendBody>) -> impl Responder {
    match mgr.send(&path.into_inner(), &body.text).await {
        Ok(_) => ok(serde_json::json!({ "status": "sent" })),
        Err(e) => err(e),
    }
}

async fn api_history(mgr: Data, path: web::Path<String>, query: web::Query<std::collections::HashMap<String, String>>) -> impl Responder {
    let since: i64 = query.get("since").and_then(|v| v.parse().ok()).unwrap_or(0);
    match mgr.history.get_history(&path.into_inner(), since).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_search(
    mgr: Data,
    path: web::Path<String>,
    query: web::Query<std::collections::HashMap<String, String>>,
) -> impl Responder {
    let q = query.get("query").cloned().unwrap_or_default();
    match mgr.search(&path.into_inner(), &q).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

// Alerts
async fn api_alerts(
    mgr: Data,
    query: web::Query<std::collections::HashMap<String, String>>,
) -> impl Responder {
    let scope = query.get("scope").map(|s| s.as_str());
    let terminal_id = query.get("terminal_id").map(|s| s.as_str());
    match mgr.list_alerts(scope, terminal_id).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct AlertBody {
    scope: String,
    pattern: String,
    #[serde(default)]
    terminal_id: Option<String>,
    #[serde(default)]
    label: Option<String>,
}

async fn api_alert_create(mgr: Data, body: web::Json<AlertBody>) -> impl Responder {
    match mgr
        .add_alert(&body.scope, &body.pattern, body.terminal_id.as_deref(), body.label.as_deref())
        .await
    {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_alert_remove(mgr: Data, path: web::Path<String>) -> impl Responder {
    let alert_id = path.into_inner();
    match mgr.remove_alert(&alert_id).await {
        Ok(removed) => ok(serde_json::json!({ "removed": removed, "alert_id": alert_id })),
        Err(e) => err(e),
    }
}

async fn api_alert_events(
    mgr: Data,
    query: web::Query<std::collections::HashMap<String, String>>,
) -> impl Responder {
    let terminal_id = query.get("terminal_id").map(|s| s.as_str());
    let since: i64 = query.get("since").and_then(|v| v.parse().ok()).unwrap_or(0);
    match mgr.list_alert_events(terminal_id, since).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

// Workspaces
async fn api_workspaces(mgr: Data) -> impl Responder {
    match mgr.list_workspaces().await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct WorkspaceCreateBody {
    workspace_id: String,
    #[serde(default)]
    env: Option<std::collections::HashMap<String, String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
}

async fn api_workspace_create(mgr: Data, body: web::Json<WorkspaceCreateBody>) -> impl Responder {
    match mgr.create_workspace(&body.workspace_id, body.env.clone(), body.startup_commands.clone()).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_workspace_get(mgr: Data, path: web::Path<String>) -> impl Responder {
    match mgr.workspace_status(&path.into_inner()).await {
        Ok(v) => ok(v),
        Err(e) => not_found(e),
    }
}

#[derive(Deserialize)]
struct WorkspaceUpdateBody {
    #[serde(default)]
    set_env: Option<std::collections::HashMap<String, String>>,
    #[serde(default)]
    unset_env: Option<Vec<String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
    #[serde(default)]
    apply_to_members: Option<bool>,
}

async fn api_workspace_update(
    mgr: Data,
    path: web::Path<String>,
    body: web::Json<WorkspaceUpdateBody>,
) -> impl Responder {
    match mgr
        .configure_workspace(
            &path.into_inner(),
            body.set_env.clone(),
            body.unset_env.clone(),
            body.startup_commands.clone(),
            body.apply_to_members.unwrap_or(true),
        )
        .await
    {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_workspace_add_member(
    mgr: Data,
    path: web::Path<String>,
    body: web::Json<serde_json::Value>,
) -> impl Responder {
    let ws_id = path.into_inner();
    let terminal_id = body.get("terminal_id").and_then(|v| v.as_str()).unwrap_or("");
    match mgr.add_terminal_to_workspace(&ws_id, terminal_id).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_workspace_remove_member(
    mgr: Data,
    path: web::Path<(String, String)>,
) -> impl Responder {
    let (ws_id, tid) = path.into_inner();
    match mgr.remove_terminal_from_workspace(&ws_id, &tid).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_workspace_apply(mgr: Data, path: web::Path<String>) -> impl Responder {
    match mgr.apply_workspace_to(&path.into_inner(), None).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

// Checkpoints
async fn api_checkpoints(
    mgr: Data,
    query: web::Query<std::collections::HashMap<String, String>>,
) -> impl Responder {
    let terminal_id = query.get("terminal_id").map(|s| s.as_str());
    match mgr.list_checkpoints(terminal_id).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct CheckpointBody {
    terminal_id: String,
    label: String,
    #[serde(default)]
    note: Option<String>,
    #[serde(default)]
    cursor: Option<i64>,
}

async fn api_checkpoint_create(mgr: Data, body: web::Json<CheckpointBody>) -> impl Responder {
    match mgr
        .add_checkpoint(&body.terminal_id, &body.label, body.note.as_deref(), body.cursor)
        .await
    {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

async fn api_checkpoint_remove(mgr: Data, path: web::Path<String>) -> impl Responder {
    let id = path.into_inner();
    match mgr.remove_checkpoint(&id).await {
        Ok(removed) => ok(serde_json::json!({ "removed": removed, "checkpoint_id": id })),
        Err(e) => err(e),
    }
}

// Export / Import
async fn api_export(mgr: Data, path: web::Path<String>) -> impl Responder {
    match mgr.export_session(&path.into_inner()).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

#[derive(Deserialize)]
struct ImportBody {
    snapshot: Value,
    #[serde(default)]
    terminal_id: Option<String>,
}

async fn api_import(mgr: Data, body: web::Json<ImportBody>) -> impl Responder {
    match mgr.import_session(&body.snapshot, body.terminal_id.as_deref()).await {
        Ok(v) => ok(v),
        Err(e) => err(e),
    }
}

// ── WebSocket (JSON protocol, matching Python) ────────────────────────────────

#[derive(serde::Deserialize)]
struct WsParams {
    since: Option<i64>,
}

async fn ws_terminal(
    mgr: Data,
    path: web::Path<String>,
    params: web::Query<WsParams>,
    req: HttpRequest,
    body: web::Payload,
) -> actix_web::Result<impl Responder> {
    let id = path.into_inner();
    let since = params.since.unwrap_or(0);

    let (response, mut ws_session, mut msg_stream) = actix_ws::handle(&req, body)?;

    // Subscribe BEFORE fetching history to close the race window where PTY output
    // could arrive after the history snapshot but before we subscribe.
    let live = mgr.get(&id).ok();
    let bcast_rx = live.as_ref().map(|s| s.subscribe());

    // PTY → WS: send history+status then relay live output (all in one task)
    let mut ws_send = ws_session.clone();
    let mgr2 = mgr.clone();
    let id2 = id.clone();
    let live2 = live.clone();
    actix_web::rt::spawn(async move {
        let history = mgr2.history.get_history(&id2, since).await
            .unwrap_or_else(|_| serde_json::json!({ "events": [], "cursor": 0 }));
        let status = mgr2.status(&id2).await
            .unwrap_or_else(|_| serde_json::json!({ "id": &id2, "alive": false }));

        let init_history = serde_json::json!({
            "type": "history",
            "events": history.get("events").cloned().unwrap_or_default(),
            "cursor": history.get("cursor").cloned().unwrap_or_default(),
        });
        let init_status = serde_json::json!({ "type": "status", "status": status });

        if ws_send.text(serde_json::to_string(&init_history).unwrap_or_default()).await.is_err() {
            return;
        }
        if ws_send.text(serde_json::to_string(&init_status).unwrap_or_default()).await.is_err() {
            return;
        }

        // Dead terminal: history sent, nothing more to stream
        let (session, mut bcast_rx) = match (live2, bcast_rx) {
            (Some(s), Some(rx)) => (s, rx),
            _ => return,
        };

        loop {
            match bcast_rx.recv().await {
                Ok(data) => {
                    let text = String::from_utf8_lossy(&data);
                    let cursor = *session.cursor.lock().await;
                    let msg = serde_json::json!({
                        "type": "output",
                        "text": text,
                        "cursor": cursor,
                        "timestamp": chrono::Utc::now().to_rfc3339(),
                    });
                    if ws_send.text(serde_json::to_string(&msg).unwrap_or_default()).await.is_err() {
                        break;
                    }
                }
                Err(broadcast::error::RecvError::Closed) => break,
                Err(broadcast::error::RecvError::Lagged(_)) => continue,
            }
        }
    });

    // WS → PTY
    actix_web::rt::spawn(async move {
        while let Some(Ok(msg)) = msg_stream.recv().await {
            match msg {
                Message::Text(text) => {
                    if let Ok(val) = serde_json::from_str::<Value>(&text) {
                        match val.get("type").and_then(|t| t.as_str()) {
                            Some("input") => {
                                if let (Some(s), Some(t)) = (
                                    live.as_ref(),
                                    val.get("text").and_then(|v| v.as_str()),
                                ) {
                                    if !t.is_empty() {
                                        s.send_input(t.as_bytes().to_vec()).await;
                                    }
                                }
                            }
                            Some("resize") => {
                                if let (Some(s), Some(rows), Some(cols)) = (
                                    live.as_ref(),
                                    val.get("rows").and_then(|v| v.as_u64()),
                                    val.get("cols").and_then(|v| v.as_u64()),
                                ) {
                                    s.send_resize(rows as u16, cols as u16);
                                }
                            }
                            _ => {}
                        }
                    } else if let Some(s) = live.as_ref() {
                        s.send_input(text.as_bytes().to_vec()).await;
                    }
                }
                Message::Binary(data) => {
                    if let Some(s) = live.as_ref() {
                        s.send_input(data.to_vec()).await;
                    }
                }
                Message::Ping(bytes) => {
                    if ws_session.pong(&bytes).await.is_err() {
                        break;
                    }
                }
                Message::Close(_) => break,
                _ => {}
            }
        }
        let _ = ws_session.close(None).await;
    });

    Ok(response)
}

// ── app factory ───────────────────────────────────────────────────────────────

pub async fn run(manager: Arc<Manager>, host: &str, port: u16) -> std::io::Result<()> {
    let data = web::Data::new(manager);

    HttpServer::new(move || {
        let cors = Cors::default()
            .allow_any_origin()
            .allow_any_method()
            .allow_any_header()
            .max_age(3600);
        App::new()
            .wrap(cors)
            .app_data(data.clone())
            .app_data(web::JsonConfig::default().error_handler(|e, _| {
                let msg = e.to_string();
                actix_web::error::InternalError::from_response(
                    e,
                    HttpResponse::BadRequest().json(serde_json::json!({ "error": msg })),
                )
                .into()
            }))
            .route("/", web::get().to(index))
            .route("/api/terminals", web::get().to(api_terminals))
            .route("/api/create", web::post().to(api_create))
            .route("/api/health", web::get().to(api_health))
            .route("/api/info", web::get().to(api_info))
            .route("/api/status/{id}", web::get().to(api_status))
            .route("/api/profile/{id}", web::get().to(api_profile_get))
            .route("/api/profile/{id}", web::post().to(api_profile_update))
            .route("/api/kill/{id}", web::post().to(api_kill))
            .route("/api/terminals/{id}", web::delete().to(api_delete_terminal))
            .route("/api/rename/{id}", web::post().to(api_rename))
            .route("/api/resize/{id}", web::post().to(api_resize))
            .route("/api/signal/{id}", web::post().to(api_signal))
            .route("/api/send/{id}", web::post().to(api_send))
            .route("/api/history/{id}", web::get().to(api_history))
            .route("/api/search/{id}", web::get().to(api_search))
            .route("/api/alerts", web::get().to(api_alerts))
            .route("/api/alerts", web::post().to(api_alert_create))
            .route("/api/alerts/{id}", web::delete().to(api_alert_remove))
            .route("/api/alert-events", web::get().to(api_alert_events))
            .route("/api/workspaces", web::get().to(api_workspaces))
            .route("/api/workspaces", web::post().to(api_workspace_create))
            .route("/api/workspaces/{ws_id}", web::get().to(api_workspace_get))
            .route("/api/workspaces/{ws_id}", web::post().to(api_workspace_update))
            .route("/api/workspaces/{ws_id}/members", web::post().to(api_workspace_add_member))
            .route("/api/workspaces/{ws_id}/members/{tid}", web::delete().to(api_workspace_remove_member))
            .route("/api/workspaces/{ws_id}/apply", web::post().to(api_workspace_apply))
            .route("/api/checkpoints", web::get().to(api_checkpoints))
            .route("/api/checkpoints", web::post().to(api_checkpoint_create))
            .route("/api/checkpoints/{id}", web::delete().to(api_checkpoint_remove))
            .route("/api/export/{id}", web::get().to(api_export))
            .route("/api/import", web::post().to(api_import))
            .route("/ws/{id}", web::get().to(ws_terminal))
    })
    .bind((host, port))?
    .run()
    .await
}
