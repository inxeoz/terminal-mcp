use std::collections::HashMap;
use std::sync::Arc;

use rmcp::{
    handler::server::wrapper::Parameters,
    model::{
        CallToolResult, Content, Implementation, ProtocolVersion, ServerCapabilities, ServerInfo,
    },
    tool, tool_handler, tool_router, ErrorData as McpError, ServerHandler, ServiceExt,
};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::Value;

use crate::manager::Manager;

// ── input structs ─────────────────────────────────────────────────────────────

#[derive(Debug, Deserialize, JsonSchema, Default)]
struct Empty {}

#[derive(Debug, Deserialize, JsonSchema)]
struct TerminalId {
    terminal_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct CreateTerminalInput {
    name: String,
    #[serde(default)]
    env: Option<HashMap<String, String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
    #[serde(default)]
    workspace_id: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ConfigureTerminalInput {
    terminal_id: String,
    #[serde(default)]
    set_env: Option<HashMap<String, String>>,
    #[serde(default)]
    unset_env: Option<Vec<String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
    #[serde(default)]
    run_startup_commands: Option<bool>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct SendInputInput {
    terminal_id: String,
    text: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ReadOutputInput {
    terminal_id: String,
    #[serde(default)]
    since: Option<u64>,
    #[serde(default)]
    max_bytes: Option<u64>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct SendSignalInput {
    terminal_id: String,
    signal: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct WaitForOutput {
    terminal_id: String,
    pattern: String,
    #[serde(default)]
    timeout: Option<f64>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct SearchOutput {
    terminal_id: String,
    query: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct AddAlertInput {
    scope: String,
    pattern: String,
    #[serde(default)]
    terminal_id: Option<String>,
    #[serde(default)]
    label: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ListAlertsInput {
    #[serde(default)]
    scope: Option<String>,
    #[serde(default)]
    terminal_id: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct AlertId {
    alert_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ListAlertEvents {
    #[serde(default)]
    terminal_id: Option<String>,
    #[serde(default)]
    since: Option<i64>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct CreateWorkspaceInput {
    workspace_id: String,
    #[serde(default)]
    env: Option<HashMap<String, String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct WorkspaceId {
    workspace_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ConfigureWorkspaceInput {
    workspace_id: String,
    #[serde(default)]
    set_env: Option<HashMap<String, String>>,
    #[serde(default)]
    unset_env: Option<Vec<String>>,
    #[serde(default)]
    startup_commands: Option<Vec<String>>,
    #[serde(default)]
    apply_to_members: Option<bool>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct WorkspaceMemberInput {
    workspace_id: String,
    terminal_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ApplyWorkspaceInput {
    workspace_id: String,
    #[serde(default)]
    terminal_id: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct AddCheckpointInput {
    terminal_id: String,
    label: String,
    #[serde(default)]
    note: Option<String>,
    #[serde(default)]
    cursor: Option<i64>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ListCheckpointsInput {
    #[serde(default)]
    terminal_id: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct CheckpointId {
    checkpoint_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ImportSessionInput {
    snapshot: std::collections::HashMap<String, Value>,
    #[serde(default)]
    terminal_id: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct RenameTerminalInput {
    terminal_id: String,
    new_id: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct ResizeTerminalInput {
    terminal_id: String,
    rows: u32,
    cols: u32,
}

#[derive(Debug, Deserialize, JsonSchema)]
struct DeleteTerminalInput {
    terminal_id: String,
}

// ── helpers ───────────────────────────────────────────────────────────────────

fn ok(v: impl serde::Serialize) -> Result<CallToolResult, McpError> {
    let json = serde_json::to_string_pretty(&v)
        .map_err(|e| McpError::internal_error(e.to_string(), None))?;
    Ok(CallToolResult::success(vec![Content::text(json)]))
}

fn tool_err(msg: impl std::fmt::Display) -> Result<CallToolResult, McpError> {
    Ok(CallToolResult::success(vec![Content::text(
        serde_json::json!({ "error": msg.to_string() }).to_string(),
    )]))
}

// ── MCP server ────────────────────────────────────────────────────────────────

#[derive(Clone)]
pub struct TerminalMcpServer {
    manager: Arc<Manager>,
    tool_router: rmcp::handler::server::tool::ToolRouter<TerminalMcpServer>,
}

#[tool_router]
impl TerminalMcpServer {
    pub fn new(manager: Arc<Manager>) -> Self {
        Self { manager, tool_router: Self::tool_router() }
    }

    #[tool(description = "Create a new persistent terminal session")]
    async fn create_terminal(
        &self,
        Parameters(p): Parameters<CreateTerminalInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.create(&p.name, p.env, p.startup_commands, p.workspace_id.as_deref(), false, true).await {
            Ok(s) => ok(serde_json::json!({ "terminal_id": s.id, "status": "created" })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "List all active terminal sessions")]
    async fn list_terminals(
        &self,
        Parameters(_): Parameters<Empty>,
    ) -> Result<CallToolResult, McpError> {
        ok(self.manager.list_all().await)
    }

    #[tool(description = "Get metadata about a terminal session")]
    async fn terminal_status(
        &self,
        Parameters(p): Parameters<TerminalId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.status(&p.terminal_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Get the stored environment and startup profile for a terminal")]
    async fn terminal_profile(
        &self,
        Parameters(p): Parameters<TerminalId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.get_profile(&p.terminal_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Update terminal environment variables or startup commands")]
    async fn configure_terminal(
        &self,
        Parameters(p): Parameters<ConfigureTerminalInput>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .configure_terminal(
                &p.terminal_id,
                p.set_env,
                p.unset_env,
                p.startup_commands,
                p.run_startup_commands.unwrap_or(false),
            )
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Send text/commands to a terminal's stdin")]
    async fn send_input(
        &self,
        Parameters(p): Parameters<SendInputInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.send(&p.terminal_id, &p.text).await {
            Ok(_) => ok(serde_json::json!({ "status": "sent" })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Read incremental terminal output since a cursor position")]
    async fn read_output(
        &self,
        Parameters(p): Parameters<ReadOutputInput>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .read(
                &p.terminal_id,
                p.since.unwrap_or(0) as usize,
                p.max_bytes.map(|v| v as usize),
            )
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Send a signal (SIGINT, SIGTERM, SIGKILL) to a terminal's process group")]
    async fn send_signal(
        &self,
        Parameters(p): Parameters<SendSignalInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.signal(&p.terminal_id, &p.signal).await {
            Ok(_) => ok(serde_json::json!({ "status": "signaled" })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Destroy a terminal session and free its resources")]
    async fn kill_terminal(
        &self,
        Parameters(p): Parameters<TerminalId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.kill(&p.terminal_id).await {
            Ok(_) => ok(serde_json::json!({ "status": "killed" })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Wait until a pattern appears in terminal output")]
    async fn wait_for_output(
        &self,
        Parameters(p): Parameters<WaitForOutput>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .wait_for(&p.terminal_id, &p.pattern, p.timeout.unwrap_or(30.0))
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Search terminal history buffer for a query")]
    async fn search_output(
        &self,
        Parameters(p): Parameters<SearchOutput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.search(&p.terminal_id, &p.query).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Register a global or session-scoped output alert pattern")]
    async fn add_output_alert(
        &self,
        Parameters(p): Parameters<AddAlertInput>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .add_alert(&p.scope, &p.pattern, p.terminal_id.as_deref(), p.label.as_deref())
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "List registered output alert patterns")]
    async fn list_output_alerts(
        &self,
        Parameters(p): Parameters<ListAlertsInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.list_alerts(p.scope.as_deref(), p.terminal_id.as_deref()).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Remove an output alert pattern")]
    async fn remove_output_alert(
        &self,
        Parameters(p): Parameters<AlertId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.remove_alert(&p.alert_id).await {
            Ok(removed) => ok(serde_json::json!({ "removed": removed, "alert_id": p.alert_id })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "List output alert matches that have fired")]
    async fn list_alert_events(
        &self,
        Parameters(p): Parameters<ListAlertEvents>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .list_alert_events(p.terminal_id.as_deref(), p.since.unwrap_or(0))
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Get a health summary for sessions, alerts, and persistence")]
    async fn health_report(
        &self,
        Parameters(_): Parameters<Empty>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.health().await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Create a workspace profile")]
    async fn create_workspace(
        &self,
        Parameters(p): Parameters<CreateWorkspaceInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.create_workspace(&p.workspace_id, p.env, p.startup_commands).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "List workspace profiles")]
    async fn list_workspaces(
        &self,
        Parameters(_): Parameters<Empty>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.list_workspaces().await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Get a workspace profile and its members")]
    async fn workspace_status(
        &self,
        Parameters(p): Parameters<WorkspaceId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.workspace_status(&p.workspace_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Update a workspace profile and optionally apply it to live members")]
    async fn configure_workspace(
        &self,
        Parameters(p): Parameters<ConfigureWorkspaceInput>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .configure_workspace(
                &p.workspace_id,
                p.set_env,
                p.unset_env,
                p.startup_commands,
                p.apply_to_members.unwrap_or(true),
            )
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Add a terminal to a workspace and apply the workspace profile")]
    async fn add_terminal_to_workspace(
        &self,
        Parameters(p): Parameters<WorkspaceMemberInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.add_terminal_to_workspace(&p.workspace_id, &p.terminal_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Remove a terminal from a workspace")]
    async fn remove_terminal_from_workspace(
        &self,
        Parameters(p): Parameters<WorkspaceMemberInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.remove_terminal_from_workspace(&p.workspace_id, &p.terminal_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Apply a workspace profile to its member terminals or one terminal")]
    async fn apply_workspace(
        &self,
        Parameters(p): Parameters<ApplyWorkspaceInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.apply_workspace_to(&p.workspace_id, p.terminal_id.as_deref()).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Mark a named checkpoint at a cursor position")]
    async fn add_checkpoint(
        &self,
        Parameters(p): Parameters<AddCheckpointInput>,
    ) -> Result<CallToolResult, McpError> {
        match self
            .manager
            .add_checkpoint(&p.terminal_id, &p.label, p.note.as_deref(), p.cursor)
            .await
        {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "List named checkpoints for all terminals or one terminal")]
    async fn list_checkpoints(
        &self,
        Parameters(p): Parameters<ListCheckpointsInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.list_checkpoints(p.terminal_id.as_deref()).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Remove a checkpoint")]
    async fn remove_checkpoint(
        &self,
        Parameters(p): Parameters<CheckpointId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.remove_checkpoint(&p.checkpoint_id).await {
            Ok(removed) => ok(serde_json::json!({ "removed": removed, "checkpoint_id": p.checkpoint_id })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Export a terminal session bundle for snapshot or handoff")]
    async fn export_session(
        &self,
        Parameters(p): Parameters<TerminalId>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.export_session(&p.terminal_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Import a terminal session bundle and restore it into a live session")]
    async fn import_session(
        &self,
        Parameters(p): Parameters<ImportSessionInput>,
    ) -> Result<CallToolResult, McpError> {
        let snapshot = Value::Object(p.snapshot.into_iter().collect());
        match self.manager.import_session(&snapshot, p.terminal_id.as_deref()).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Get the web UI URL where terminal sessions can be viewed in a browser")]
    async fn web_url(
        &self,
        Parameters(_): Parameters<Empty>,
    ) -> Result<CallToolResult, McpError> {
        let url = self.manager.web_url.read().await.clone();
        ok(serde_json::json!({ "url": url }))
    }

    #[tool(description = "Rename a terminal session. Updates all history, alerts, checkpoints, and workspace memberships.")]
    async fn rename_terminal(
        &self,
        Parameters(p): Parameters<RenameTerminalInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.rename(&p.terminal_id, &p.new_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Resize the PTY dimensions for a terminal session")]
    async fn resize_terminal(
        &self,
        Parameters(p): Parameters<ResizeTerminalInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.resize(&p.terminal_id, p.rows as u16, p.cols as u16) {
            Ok(_) => ok(serde_json::json!({
                "status": "resized",
                "terminal_id": p.terminal_id,
                "rows": p.rows,
                "cols": p.cols
            })),
            Err(e) => tool_err(e),
        }
    }

    #[tool(description = "Return details about this i4z-terminal-mcp server: name, version, implementation, and web UI URL.")]
    async fn server_info(
        &self,
        Parameters(_): Parameters<Empty>,
    ) -> Result<CallToolResult, McpError> {
        let web_url = self.manager.web_url.read().await.clone();
        ok(serde_json::json!({
            "name": "i4z-terminal-mcp",
            "version": env!("CARGO_PKG_VERSION"),
            "implementation": "rust",
            "web_url": web_url,
        }))
    }

    #[tool(description = "Permanently delete a terminal session and all its history. Kills the process if still alive.")]
    async fn delete_terminal(
        &self,
        Parameters(p): Parameters<DeleteTerminalInput>,
    ) -> Result<CallToolResult, McpError> {
        match self.manager.delete_terminal(&p.terminal_id).await {
            Ok(v) => ok(v),
            Err(e) => tool_err(e),
        }
    }
}

#[tool_handler]
impl ServerHandler for TerminalMcpServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo {
            protocol_version: ProtocolVersion::LATEST,
            capabilities: ServerCapabilities::builder().enable_tools().build(),
            server_info: Implementation {
                name: "i4z-terminal-mcp".into(),
                version: env!("CARGO_PKG_VERSION").into(),
                title: None,
                icons: None,
                website_url: None,
            },
            instructions: Some(
                "Persistent PTY terminal session manager. Use create_terminal to start a session, \
                 send_input to run commands, read_output to get results."
                    .into(),
            ),
        }
    }
}

// ── entry point ───────────────────────────────────────────────────────────────

pub async fn run_mcp_server(manager: Arc<Manager>) -> anyhow::Result<()> {
    use rmcp::transport::stdio;
    let server = TerminalMcpServer::new(manager);
    let service = server.serve(stdio()).await?;
    service.waiting().await?;
    Ok(())
}
