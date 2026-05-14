use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use dashmap::DashMap;
use regex::Regex;
use serde_json::Value;
use tokio::sync::RwLock;

use crate::history::History;
use crate::session::{kill_pid, spawn_session, set_env_in_shell, unset_env_in_shell, Session, SpawnOptions};

lazy_static::lazy_static! {
    static ref ROUTE_SAFE_ID_RE: Regex = Regex::new(r"^[^\x00-\x1f\x7f/\\]+$").unwrap();
    static ref ENV_KEY_RE: Regex = Regex::new(r"^[A-Za-z_][A-Za-z0-9_]*$").unwrap();
}

fn validate_route_id(value: &str, label: &str) -> anyhow::Result<()> {
    if value.is_empty() {
        return Err(anyhow::anyhow!("{label} cannot be empty"));
    }
    if !ROUTE_SAFE_ID_RE.is_match(value) {
        return Err(anyhow::anyhow!("{label} cannot contain path separators or control characters"));
    }
    Ok(())
}

fn validate_env_key(key: &str) -> anyhow::Result<()> {
    if !ENV_KEY_RE.is_match(key) {
        return Err(anyhow::anyhow!("Invalid environment variable name: {key:?}"));
    }
    Ok(())
}

pub struct CompiledAlert {
    pub id: String,
    pub scope: String,
    pub terminal_id: Option<String>,
    pub pattern: String,
    pub label: Option<String>,
    pub regex: Regex,
}

pub struct Manager {
    pub sessions: DashMap<String, Arc<Session>>,
    pub history: Arc<History>,
    pub alerts: Arc<RwLock<Vec<CompiledAlert>>>,
    pub web_url: Arc<RwLock<String>>,
}

impl Manager {
    pub async fn new(state_dir: &str) -> anyhow::Result<Self> {
        let history = Arc::new(History::open(state_dir).await?);
        // Pre-load alerts from DB
        let db_alerts = history.list_alerts(None, None).await.unwrap_or_default();
        let compiled: Vec<CompiledAlert> = db_alerts
            .into_iter()
            .filter_map(|a| {
                Regex::new(&a.pattern).ok().map(|re| CompiledAlert {
                    id: a.id,
                    scope: a.scope,
                    terminal_id: a.terminal_id,
                    pattern: a.pattern,
                    label: a.label,
                    regex: re,
                })
            })
            .collect();
        Ok(Self {
            sessions: DashMap::new(),
            history,
            alerts: Arc::new(RwLock::new(compiled)),
            web_url: Arc::new(RwLock::new(String::new())),
        })
    }

    // ── session lifecycle ─────────────────────────────────────────────────────

    pub async fn create(
        &self,
        name: &str,
        env: Option<HashMap<String, String>>,
        startup_commands: Option<Vec<String>>,
        workspace_id: Option<&str>,
        interactive: bool,
        run_startup_commands: bool,
    ) -> anyhow::Result<Arc<Session>> {
        let name = name.trim();
        validate_route_id(name, "Terminal name")?;
        if self.sessions.contains_key(name) {
            return Err(anyhow::anyhow!("Terminal '{name}' already exists"));
        }
        if let Some(ws_id) = workspace_id {
            validate_route_id(ws_id, "Workspace id")?;
        }

        // Merge profile + workspace + runtime env
        let profile = self.history.get_profile(name).await.unwrap_or_else(|_| crate::history::Profile::default_for(name));
        let mut workspace_profile = crate::history::Profile::default_for(name);
        if let Some(ws_id) = workspace_id {
            if let Ok(Some(ws)) = self.history.get_workspace(ws_id).await {
                workspace_profile.env = ws.env;
                workspace_profile.startup_commands = ws.startup_commands;
            }
        }

        let mut merged_env = profile.env.clone();
        for (k, v) in &workspace_profile.env {
            merged_env.insert(k.clone(), v.clone());
        }
        if let Some(e) = env {
            for (k, v) in e {
                merged_env.insert(k, Value::String(v));
            }
        }

        let mut merged_cmds: Vec<String> = profile.startup_commands.clone();
        merged_cmds.extend(workspace_profile.startup_commands.clone());
        if let Some(c) = startup_commands {
            merged_cmds.extend(c);
        }

        // Save merged profile
        let saved_profile = crate::history::Profile {
            terminal_id: name.to_string(),
            env: merged_env.clone(),
            startup_commands: merged_cmds.clone(),
        };
        self.history.upsert_profile(&saved_profile).await?;
        self.history.clear_reader_error(name).await?;

        // Build spawn env (inherit common vars, then layer profile env)
        let mut env_vec: Vec<(String, String)> = vec![
            ("HOME".into(), std::env::var("HOME").unwrap_or_default()),
            ("USER".into(), std::env::var("USER").unwrap_or_default()),
            ("PATH".into(), std::env::var("PATH").unwrap_or("/usr/bin:/bin".into())),
            ("LANG".into(), std::env::var("LANG").unwrap_or("en_US.UTF-8".into())),
            ("SHELL".into(), std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".into())),
        ];
        for (k, v) in &merged_env {
            if let Value::String(s) = v {
                env_vec.push((k.clone(), s.clone()));
            }
        }

        let session = spawn_session(
            SpawnOptions { id: name.to_string(), env: env_vec, rows: 24, cols: 80, interactive },
            self.history.clone(),
            self.alerts.clone(),
        )
        .await?;

        let session = Arc::new(session);
        self.sessions.insert(name.to_string(), session.clone());

        // Add to workspace
        if let Some(ws_id) = workspace_id {
            let _ = self.history.add_workspace_member(ws_id, name).await;
        }

        // Run startup commands
        if run_startup_commands && !merged_cmds.is_empty() {
            for cmd in &merged_cmds {
                let trimmed = cmd.trim();
                if !trimmed.is_empty() {
                    let mut line = trimmed.to_string();
                    if !line.ends_with('\n') && !line.ends_with('\r') {
                        line.push('\n');
                    }
                    session.send_input(line.into_bytes()).await;
                    let _ = self.history.record_input(name, trimmed).await;
                }
            }
        }

        Ok(session)
    }

    pub async fn kill(&self, id: &str) -> anyhow::Result<()> {
        if let Some((_, session)) = self.sessions.remove(id) {
            session.alive.store(false, std::sync::atomic::Ordering::Relaxed);
            let _ = session.kill_tx.send(()).await;
            if let Some(handle) = session.reader_handle.lock().await.take() {
                let _ = handle.await;
            }
        }
        Ok(())
    }

    pub async fn delete_terminal(&self, id: &str) -> anyhow::Result<serde_json::Value> {
        self.kill(id).await?;
        self.history.delete_terminal(id).await?;
        Ok(serde_json::json!({ "id": id, "deleted": true }))
    }

    pub fn get(&self, id: &str) -> anyhow::Result<Arc<Session>> {
        self.sessions
            .get(id)
            .map(|r| r.value().clone())
            .ok_or_else(|| anyhow::anyhow!("Terminal '{id}' not found"))
    }

    pub async fn list_all(&self) -> Vec<serde_json::Value> {
        let mut active: HashMap<String, serde_json::Value> = HashMap::new();
        for r in self.sessions.iter() {
            let s = r.value();
            active.insert(s.id.clone(), serde_json::json!({
                "id": s.id,
                "alive": s.is_alive(),
            }));
        }
        // Include dead terminals from history
        if let Ok(ids) = self.history.list_terminal_ids().await {
            for tid in ids {
                if !active.contains_key(&tid) {
                    active.insert(tid.clone(), serde_json::json!({
                        "id": tid,
                        "alive": false,
                    }));
                }
            }
        }
        active.into_values().collect()
    }

    pub async fn status(&self, id: &str) -> anyhow::Result<serde_json::Value> {
        if let Some(s) = self.sessions.get(id) {
            let s = s.value();
            let cwd = s.get_cwd();
            let reader_error = self.history.get_reader_error(id).await.ok().flatten();
            let profile = self.history.get_profile(id).await.ok();
            let workspace_ids = self.history.list_workspace_ids_for_terminal(id).await.ok().unwrap_or_default();
            return Ok(serde_json::json!({
                "id": s.id,
                "alive": s.is_alive(),
                "pid": s.pid,
                "cwd": cwd,
                "created_at": s.created_at,
                "last_activity": s.updated_at.lock().await.clone(),
                "reader_error": reader_error,
                "profile": profile,
                "workspaces": workspace_ids,
            }));
        }
        // Fallback to history for dead terminals
        match self.history.status(id).await {
            Ok(mut data) => {
                let profile = self.history.get_profile(id).await.ok();
                let workspace_ids = self.history.list_workspace_ids_for_terminal(id).await.ok().unwrap_or_default();
                if let Some(obj) = data.as_object_mut() {
                    obj.insert("profile".into(), serde_json::to_value(profile).unwrap_or_default());
                    obj.insert("workspaces".into(), serde_json::to_value(workspace_ids).unwrap_or_default());
                }
                Ok(data)
            }
            Err(e) => Err(anyhow::anyhow!("{e}")),
        }
    }

    pub async fn rename(&self, old_id: &str, new_id: &str) -> anyhow::Result<serde_json::Value> {
        let new_id = new_id.trim();
        validate_route_id(new_id, "Terminal name")?;
        if new_id == old_id {
            return Ok(serde_json::json!({ "old_id": old_id, "new_id": new_id }));
        }
        if self.sessions.contains_key(new_id) {
            return Err(anyhow::anyhow!("Terminal '{new_id}' already exists"));
        }
        if let Some((_, session)) = self.sessions.remove(old_id) {
            let new_session = Arc::new(Session {
                id: new_id.to_string(),
                pid: session.pid,
                alive: session.alive.clone(),
                created_at: session.created_at,
                updated_at: session.updated_at.clone(),
                write_tx: session.write_tx.clone(),
                resize_tx: session.resize_tx.clone(),
                kill_tx: session.kill_tx.clone(),
                reader_handle: session.reader_handle.clone(),
                output: session.output.clone(),
                cursor: session.cursor.clone(),
                output_notify: session.output_notify.clone(),
                output_bcast: session.output_bcast.clone(),
            });
            self.sessions.insert(new_id.to_string(), new_session);
        }
        self.history.rename_terminal(old_id, new_id).await?;
        Ok(serde_json::json!({ "old_id": old_id, "new_id": new_id }))
    }

    pub fn resize(&self, id: &str, rows: u16, cols: u16) -> anyhow::Result<()> {
        let s = self.get(id)?;
        s.send_resize(rows.max(1), cols.max(1));
        Ok(())
    }

    // ── I/O ───────────────────────────────────────────────────────────────────

    pub async fn send(&self, id: &str, text: &str) -> anyhow::Result<()> {
        let s = self.get(id)?;
        if !s.is_alive() {
            return Err(anyhow::anyhow!("Terminal '{id}' is dead"));
        }
        let send_text = if text.ends_with('\n') || text.ends_with('\r') {
            text.to_string()
        } else {
            format!("{text}\n")
        };
        s.send_input(send_text.into_bytes()).await;
        // Record input in history
        self.history.record_input(id, text).await?;
        Ok(())
    }

    pub async fn send_raw(&self, id: &str, data: &[u8]) -> anyhow::Result<()> {
        self.get(id)?.send_input(data.to_vec()).await;
        Ok(())
    }

    pub async fn read(&self, id: &str, since: usize, max_bytes: Option<usize>) -> anyhow::Result<serde_json::Value> {
        let s = self.get(id)?;
        let (output, cursor) = s.read_output(since, max_bytes).await;
        Ok(serde_json::json!({
            "output": output,
            "cursor": cursor,
        }))
    }

    pub async fn wait_for(
        &self,
        id: &str,
        pattern: &str,
        timeout_secs: f64,
    ) -> anyhow::Result<serde_json::Value> {
        let s = self.get(id)?;
        let deadline = tokio::time::Instant::now()
            + Duration::from_secs_f64(timeout_secs.max(0.1));

        loop {
            {
                let buf = s.output.lock().await;
                let mut text = String::new();
                for entry in buf.iter() {
                    text.push_str(&entry.text);
                }
                if text.contains(pattern) {
                    let cursor = *s.cursor.lock().await;
                    return Ok(serde_json::json!({ "matched": true, "cursor": cursor }));
                }
            }
            if tokio::time::Instant::now() >= deadline {
                let cursor = *s.cursor.lock().await;
                return Ok(serde_json::json!({ "matched": false, "cursor": cursor }));
            }
            tokio::select! {
                _ = s.output_notify.notified() => {}
                _ = tokio::time::sleep_until(deadline) => {
                    let cursor = *s.cursor.lock().await;
                    return Ok(serde_json::json!({ "matched": false, "cursor": cursor }));
                }
            }
        }
    }

    pub async fn search(&self, id: &str, query: &str) -> anyhow::Result<serde_json::Value> {
        // Check live session first
        if let Some(s) = self.sessions.get(id) {
            let matches = s.value().search_output(query).await;
            if !matches.is_empty() {
                return Ok(serde_json::json!({ "matches": matches }));
            }
        }
        // Fallback to history DB
        self.history.search(id, query).await
    }

    pub async fn signal(&self, id: &str, sig: &str) -> anyhow::Result<()> {
        let s = self.get(id)?;
        kill_pid(s.pid, sig)?;
        Ok(())
    }

    // ── profiles ──────────────────────────────────────────────────────────────

    pub async fn get_profile(&self, id: &str) -> anyhow::Result<serde_json::Value> {
        let profile = self.history.get_profile(id).await?;
        Ok(serde_json::to_value(profile)?)
    }

    pub async fn configure_terminal(
        &self,
        id: &str,
        set_env: Option<HashMap<String, String>>,
        unset_env: Option<Vec<String>>,
        startup_commands: Option<Vec<String>>,
        run_startup: bool,
    ) -> anyhow::Result<serde_json::Value> {
        let mut profile = self.history.get_profile(id).await?;

        // Apply set_env to DB and live shell
        if let Some(env) = set_env {
            for (k, v) in &env {
                validate_env_key(k)?;
                profile.env.insert(k.clone(), Value::String(v.clone()));
                // Send to running shell
                if let Ok(s) = self.get(id) {
                    set_env_in_shell(&s, k, v).await;
                }
            }
        }
        // Apply unset_env to DB and live shell
        if let Some(keys) = unset_env {
            for k in &keys {
                validate_env_key(k)?;
                profile.env.remove(k);
                // Send to running shell
                if let Ok(s) = self.get(id) {
                    unset_env_in_shell(&s, k).await;
                }
            }
        }
        if let Some(cmds) = startup_commands {
            profile.startup_commands = cmds;
        }
        self.history.upsert_profile(&profile).await?;

        // Run startup commands if requested
        if run_startup {
            if let Ok(s) = self.get(id) {
                for cmd in &profile.startup_commands {
                    let trimmed = cmd.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    let mut line = trimmed.to_string();
                    if !line.ends_with('\n') && !line.ends_with('\r') {
                        line.push('\n');
                    }
                    s.send_input(line.into_bytes()).await;
                    let _ = self.history.record_input(id, trimmed).await;
                }
            }
        }

        Ok(serde_json::to_value(profile)?)
    }

    // ── alerts ────────────────────────────────────────────────────────────────

    pub async fn add_alert(
        &self,
        scope: &str,
        pattern: &str,
        terminal_id: Option<&str>,
        label: Option<&str>,
    ) -> anyhow::Result<serde_json::Value> {
        if scope == "session" && terminal_id.is_none() {
            return Err(anyhow::anyhow!("terminal_id is required for session alerts"));
        }
        if scope == "global" {
            // global alerts have null terminal_id
        }
        let re = Regex::new(pattern)?;
        let id = self.history.add_alert(scope, pattern, terminal_id, label).await?;
        let mut cache = self.alerts.write().await;
        cache.push(CompiledAlert {
            id: id.clone(),
            scope: scope.to_string(),
            terminal_id: terminal_id.map(String::from),
            pattern: pattern.to_string(),
            label: label.map(String::from),
            regex: re,
        });
        Ok(serde_json::json!({ "id": id, "scope": scope, "pattern": pattern, "terminal_id": terminal_id, "label": label }))
    }

    pub async fn list_alerts(
        &self,
        scope: Option<&str>,
        terminal_id: Option<&str>,
    ) -> anyhow::Result<serde_json::Value> {
        let alerts = self.history.list_alerts(scope, terminal_id).await?;
        Ok(serde_json::to_value(alerts)?)
    }

    pub async fn remove_alert(&self, alert_id: &str) -> anyhow::Result<bool> {
        let removed = self.history.remove_alert(alert_id).await?;
        if removed {
            let mut cache = self.alerts.write().await;
            cache.retain(|a| a.id != alert_id);
        }
        Ok(removed)
    }

    pub async fn list_alert_events(
        &self,
        terminal_id: Option<&str>,
        since: i64,
    ) -> anyhow::Result<serde_json::Value> {
        let events = self.history.list_alert_events(terminal_id, since).await?;
        Ok(serde_json::to_value(events)?)
    }

    // ── workspaces ────────────────────────────────────────────────────────────

    pub async fn create_workspace(
        &self,
        id: &str,
        env: Option<HashMap<String, String>>,
        startup_commands: Option<Vec<String>>,
    ) -> anyhow::Result<serde_json::Value> {
        validate_route_id(id, "Workspace id")?;
        let env_map: serde_json::Map<String, Value> = env
            .unwrap_or_default()
            .into_iter()
            .map(|(k, v)| (k, Value::String(v)))
            .collect();
        let cmds = startup_commands.unwrap_or_default();
        self.history.create_workspace(id, &env_map, &cmds).await?;
        Ok(serde_json::json!({ "id": id, "status": "created" }))
    }

    pub async fn list_workspaces(&self) -> anyhow::Result<serde_json::Value> {
        let ws = self.history.list_workspaces().await?;
        Ok(serde_json::to_value(ws)?)
    }

    pub async fn workspace_status(&self, id: &str) -> anyhow::Result<serde_json::Value> {
        self.history
            .get_workspace(id)
            .await?
            .map(|w| serde_json::to_value(w).unwrap())
            .ok_or_else(|| anyhow::anyhow!("Workspace '{id}' not found"))
    }

    pub async fn configure_workspace(
        &self,
        id: &str,
        set_env: Option<HashMap<String, String>>,
        unset_env: Option<Vec<String>>,
        startup_commands: Option<Vec<String>>,
        apply_to_members: bool,
    ) -> anyhow::Result<serde_json::Value> {
        let mut ws = self
            .history
            .get_workspace(id)
            .await?
            .ok_or_else(|| anyhow::anyhow!("Workspace '{id}' not found"))?;

        if let Some(env) = &set_env {
            for k in env.keys() {
                validate_env_key(k)?;
            }
            for (k, v) in env {
                ws.env.insert(k.to_string(), Value::String(v.to_string()));
            }
        }
        if let Some(keys) = &unset_env {
            for k in keys {
                ws.env.remove(k);
            }
        }
        if let Some(cmds) = startup_commands {
            ws.startup_commands = cmds;
        }
        self.history.update_workspace(id, &ws.env, &ws.startup_commands).await?;

        let mut applied: Vec<String> = Vec::new();
        if apply_to_members {
            for member in &ws.members {
                if let Ok(s) = self.get(member) {
                    for (k, v) in &ws.env {
                        if let Value::String(val) = v {
                            set_env_in_shell(&s, k, val).await;
                        }
                    }
                    for cmd in &ws.startup_commands {
                        let trimmed = cmd.trim();
                        if trimmed.is_empty() {
                            continue;
                        }
                        let mut line = trimmed.to_string();
                        if !line.ends_with('\n') && !line.ends_with('\r') {
                            line.push('\n');
                        }
                        s.send_input(line.into_bytes()).await;
                        let _ = self.history.record_input(member, trimmed).await;
                    }
                    applied.push(member.clone());
                }
            }
        }
        let mut result = serde_json::to_value(&ws).unwrap_or_default();
        if let Some(obj) = result.as_object_mut() {
            obj.insert("applied_to".into(), serde_json::json!(applied));
        }
        Ok(result)
    }

    pub async fn add_terminal_to_workspace(
        &self,
        workspace_id: &str,
        terminal_id: &str,
    ) -> anyhow::Result<serde_json::Value> {
        self.history.add_workspace_member(workspace_id, terminal_id).await?;
        // Apply workspace env/startup to the terminal if it's live
        if let Ok(s) = self.get(terminal_id) {
            if let Ok(Some(ws)) = self.history.get_workspace(workspace_id).await {
                self.apply_workspace_to_session(&s, &ws).await;
            }
        }
        self.workspace_status(workspace_id).await
    }

    pub async fn remove_terminal_from_workspace(
        &self,
        workspace_id: &str,
        terminal_id: &str,
    ) -> anyhow::Result<serde_json::Value> {
        self.history.remove_workspace_member(workspace_id, terminal_id).await?;
        self.workspace_status(workspace_id).await
    }

    pub async fn apply_workspace_to(
        &self,
        workspace_id: &str,
        only_terminal: Option<&str>,
    ) -> anyhow::Result<serde_json::Value> {
        let ws = self
            .history
            .get_workspace(workspace_id)
            .await?
            .ok_or_else(|| anyhow::anyhow!("Workspace '{workspace_id}' not found"))?;

        let targets: Vec<String> = if let Some(t) = only_terminal {
            vec![t.to_string()]
        } else {
            ws.members.clone()
        };

        let mut applied: Vec<String> = Vec::new();
        for tid in &targets {
            if let Ok(s) = self.get(tid) {
                self.apply_workspace_to_session(&s, &ws).await;
                applied.push(tid.clone());
            }
        }

        Ok(serde_json::json!({ "workspace_id": workspace_id, "applied_to": applied, "workspace": ws }))
    }

    async fn apply_workspace_to_session(&self, session: &Session, workspace: &crate::history::Workspace) {
        for (k, v) in &workspace.env {
            if let Value::String(val) = v {
                set_env_in_shell(session, k, val).await;
            }
        }
        for cmd in &workspace.startup_commands {
            let trimmed = cmd.trim();
            if trimmed.is_empty() {
                continue;
            }
            let mut line = trimmed.to_string();
            if !line.ends_with('\n') && !line.ends_with('\r') {
                line.push('\n');
            }
            session.send_input(line.into_bytes()).await;
            let _ = self.history.record_input(&session.id, trimmed).await;
        }
    }

    // ── checkpoints ───────────────────────────────────────────────────────────

    pub async fn add_checkpoint(
        &self,
        terminal_id: &str,
        label: &str,
        note: Option<&str>,
        cursor: Option<i64>,
    ) -> anyhow::Result<serde_json::Value> {
        let s = self.get(terminal_id)?;
        let cur = if let Some(c) = cursor { c } else { *s.cursor.lock().await as i64 };
        let id = self.history.add_checkpoint(terminal_id, label, note, Some(cur)).await?;
        Ok(serde_json::json!({ "id": id, "terminal_id": terminal_id, "label": label, "cursor": cur, "note": note }))
    }

    pub async fn list_checkpoints(&self, terminal_id: Option<&str>) -> anyhow::Result<serde_json::Value> {
        let cps = self.history.list_checkpoints(terminal_id).await?;
        Ok(serde_json::to_value(cps)?)
    }

    pub async fn remove_checkpoint(&self, id: &str) -> anyhow::Result<bool> {
        self.history.remove_checkpoint(id).await
    }

    // ── export / import ───────────────────────────────────────────────────────

    pub async fn export_session(&self, id: &str) -> anyhow::Result<serde_json::Value> {
        let profile = self.history.get_profile(id).await.ok();
        let history = self.history.get_history(id, 0).await.ok();
        let workspace_ids = self.history.list_workspace_ids_for_terminal(id).await.ok().unwrap_or_default();
        let mut data = serde_json::json!({
            "terminal_id": id,
            "profile": profile,
            "history": history,
            "alerts": [],
            "checkpoints": [],
            "workspaces": workspace_ids,
            "workspace_profiles": [],
        });
        // Add session-scoped alerts
        if let Ok(alerts) = self.history.list_alerts(None, Some(id)).await {
            if let Some(obj) = data.as_object_mut() {
                obj.insert("alerts".into(), serde_json::to_value(alerts).unwrap_or_default());
            }
        }
        // Add status if live
        if let Ok(s) = self.get(id) {
            if let Some(obj) = data.as_object_mut() {
                obj.insert("status".into(), serde_json::json!({
                    "id": s.id,
                    "alive": s.is_alive(),
                    "pid": s.pid,
                    "created_at": s.created_at,
                    "last_activity": *s.updated_at.lock().await,
                }));
            }
        }
        // Add checkpoints
        if let Ok(cps) = self.history.list_checkpoints(Some(id)).await {
            if let Some(obj) = data.as_object_mut() {
                obj.insert("checkpoints".into(), serde_json::to_value(cps).unwrap_or_default());
            }
        }
        // Add workspace profiles
        let mut ws_profiles = Vec::new();
        for ws_id in &workspace_ids {
            if let Ok(Some(ws)) = self.history.get_workspace(ws_id).await {
                ws_profiles.push(serde_json::to_value(ws).unwrap_or_default());
            }
        }
        if let Some(obj) = data.as_object_mut() {
            obj.insert("workspace_profiles".into(), serde_json::json!(ws_profiles));
        }
        Ok(data)
    }

    pub async fn import_session(
        &self,
        snapshot: &serde_json::Value,
        new_id: Option<&str>,
    ) -> anyhow::Result<serde_json::Value> {
        let source_id = snapshot["terminal_id"].as_str().unwrap_or("session");
        let target_id = new_id.unwrap_or(source_id).to_string();
        if self.sessions.contains_key(&target_id) {
            return Err(anyhow::anyhow!("Terminal '{target_id}' already exists"));
        }

        let profile = snapshot.get("profile");
        let env: HashMap<String, String> = profile
            .and_then(|p| p.get("env"))
            .and_then(|e| serde_json::from_value(e.clone()).ok())
            .unwrap_or_default();
        let startup_cmds: Vec<String> = profile
            .and_then(|p| p.get("startup_commands"))
            .and_then(|c| serde_json::from_value(c.clone()).ok())
            .unwrap_or_default();

        let session = self.create(&target_id, Some(env), None, None, false, false).await?;

        // Replay input events
        let events = snapshot
            .get("history")
            .and_then(|h| h.get("events"))
            .and_then(|e| e.as_array())
            .cloned()
            .unwrap_or_default();
        for event in &events {
            if event.get("type").and_then(|t| t.as_str()) == Some("input") {
                if let Some(text) = event.get("text").and_then(|t| t.as_str()) {
                    self.send(&target_id, text).await?;
                    let _ = tokio::time::timeout(
                        Duration::from_millis(200),
                        session.output_notify.notified(),
                    ).await;
                }
            }
        }

        // Set startup commands
        if !startup_cmds.is_empty() {
            let mut p = self.history.get_profile(&target_id).await.unwrap_or_else(|_| crate::history::Profile::default_for(&target_id));
            p.startup_commands = startup_cmds;
            let _ = self.history.upsert_profile(&p).await;
        }

        // Restore checkpoints
        if let Some(checkpoints) = snapshot.get("checkpoints").and_then(|c| c.as_array()) {
            for cp in checkpoints {
                let label = cp.get("label").and_then(|l| l.as_str()).unwrap_or("checkpoint");
                let cursor = cp.get("cursor").and_then(|c| c.as_i64());
                let note = cp.get("note").and_then(|n| n.as_str());
                let _ = self.history.add_checkpoint(&target_id, label, note, cursor).await;
            }
        }

        // Restore alerts
        if let Some(alerts) = snapshot.get("alerts").and_then(|a| a.as_array()) {
            for alert in alerts {
                if alert.get("scope").and_then(|s| s.as_str()) == Some("session") {
                    let pattern = alert.get("pattern").and_then(|p| p.as_str()).unwrap_or("");
                    let label = alert.get("label").and_then(|l| l.as_str());
                    let _ = self.add_alert("session", pattern, Some(&target_id), label).await;
                }
            }
        }

        // Restore workspace memberships
        if let Some(ws_profiles) = snapshot.get("workspace_profiles").and_then(|w| w.as_array()) {
            for ws in ws_profiles {
                let ws_id = ws.get("id").and_then(|i| i.as_str()).unwrap_or("").trim();
                if ws_id.is_empty() {
                    continue;
                }
                if self.history.get_workspace(ws_id).await.ok().flatten().is_none() {
                    let ws_env = ws.get("env").and_then(|e| serde_json::from_value(e.clone()).ok()).unwrap_or_default();
                    let ws_cmds: Vec<String> = ws.get("startup_commands").and_then(|c| serde_json::from_value(c.clone()).ok()).unwrap_or_default();
                    let _ = self.history.create_workspace(ws_id, &ws_env, &ws_cmds).await;
                }
                let _ = self.history.add_workspace_member(ws_id, &target_id).await;
                let _ = self.apply_workspace_to(ws_id, Some(&target_id)).await;
            }
        } else if let Some(ws_ids) = snapshot.get("workspaces").and_then(|w| w.as_array()) {
            for ws_id in ws_ids {
                if let Some(id_str) = ws_id.as_str() {
                    if self.history.get_workspace(id_str).await.is_ok() {
                        let _ = self.history.add_workspace_member(id_str, &target_id).await;
                        let _ = self.apply_workspace_to(id_str, Some(&target_id)).await;
                    }
                }
            }
        }

        Ok(serde_json::json!({ "terminal_id": session.id, "status": "imported" }))
    }

    // ── health ────────────────────────────────────────────────────────────────

    pub async fn health(&self) -> anyhow::Result<serde_json::Value> {
        let counts = self.history.counts().await?;
        let mut active_list: Vec<serde_json::Value> = Vec::new();
        for r in self.sessions.iter() {
            let s = r.value();
            active_list.push(serde_json::json!({
                "id": s.id,
                "alive": s.is_alive(),
                "pid": s.pid,
                "last_activity": *s.updated_at.lock().await,
            }));
        }
        let known = self.history.list_terminal_ids().await.unwrap_or_default();
        Ok(serde_json::json!({
            "db": { "path": "history.db", "ok": true },
            "counts": counts,
            "sessions": {
                "active": active_list.len(),
                "stale": [],
                "known": known,
            },
        }))
    }

    pub async fn shutdown(&self) -> anyhow::Result<()> {
        for r in self.sessions.iter() {
            r.value().kill().await;
        }
        Ok(())
    }

    // ── server config ─────────────────────────────────────────────────────────

    /// Defaults used when a key has never been explicitly set.
    pub fn config_defaults() -> std::collections::HashMap<&'static str, u64> {
        [
            ("sidebar_refresh_ms", 3000u64),
            ("health_check_ms",    8000),
            ("alert_events_ms",    7000),
            ("ws_reconnect_ms",    1500),
        ]
        .into_iter()
        .collect()
    }

    pub async fn get_all_config(&self) -> anyhow::Result<serde_json::Value> {
        let stored = self.history.all_config().await?;
        let defaults = Self::config_defaults();
        let mut out = serde_json::Map::new();
        for (k, def) in &defaults {
            let v: u64 = stored
                .get(*k)
                .and_then(|s| s.parse().ok())
                .unwrap_or(*def);
            out.insert(k.to_string(), serde_json::json!(v));
        }
        Ok(serde_json::Value::Object(out))
    }

    pub async fn set_config_values(&self, updates: std::collections::HashMap<String, u64>) -> anyhow::Result<serde_json::Value> {
        let defaults = Self::config_defaults();
        let mut applied = serde_json::Map::new();
        for (k, v) in updates {
            if !defaults.contains_key(k.as_str()) {
                return Err(anyhow::anyhow!("Unknown config key: {k}"));
            }
            self.history.set_config(&k, &v.to_string()).await?;
            applied.insert(k, serde_json::json!(v));
        }
        self.get_all_config().await
    }
}
