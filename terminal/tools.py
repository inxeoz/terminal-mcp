from mcp.types import Tool

TOOLS = [
    Tool(
        name="create_terminal",
        description="Create a new persistent terminal session",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "minLength": 1, "description": "Unique name for the terminal"},
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Environment variables to apply when the session starts",
                },
                "startup_commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Commands to run after the shell starts",
                },
                "workspace_id": {
                    "type": "string",
                    "description": "Optional workspace preset to seed the session from",
                },
            },
            "required": ["name"],
        },
    ),
    Tool(
        name="list_terminals",
        description="List all active terminal sessions",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="terminal_status",
        description="Get metadata about a terminal session",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"}
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="terminal_profile",
        description="Get the stored environment and startup profile for a terminal",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"}
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="configure_terminal",
        description="Update terminal environment variables or startup commands",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "set_env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Environment variables to add or update",
                },
                "unset_env": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Environment variable names to remove",
                },
                "startup_commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replace the stored startup commands",
                },
                "run_startup_commands": {
                    "type": "boolean",
                    "description": "Run the stored or provided startup commands immediately",
                    "default": False,
                },
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="send_input",
        description="Send text/commands to a terminal's stdin",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "text": {"type": "string", "description": "Text to send (newline optional for commands)"},
            },
            "required": ["terminal_id", "text"],
        },
    ),
    Tool(
        name="read_output",
        description="Read incremental terminal output since a cursor position",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "since": {"type": "integer", "description": "Cursor offset to read from", "default": 0},
                "max_bytes": {"type": "integer", "description": "Maximum bytes to return"},
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="send_signal",
        description="Send a signal (SIGINT, SIGTERM, SIGKILL) to a terminal's process group",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "signal": {
                    "type": "string",
                    "description": "Signal name",
                    "enum": ["SIGINT", "SIGTERM", "SIGKILL"],
                },
            },
            "required": ["terminal_id", "signal"],
        },
    ),
    Tool(
        name="kill_terminal",
        description="Destroy a terminal session and free its resources",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"}
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="wait_for_output",
        description="Wait until a pattern appears in terminal output",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "pattern": {"type": "string", "description": "Pattern to wait for"},
                "timeout": {"type": "number", "description": "Timeout in seconds", "default": 30},
            },
            "required": ["terminal_id", "pattern"],
        },
    ),
    Tool(
        name="search_output",
        description="Search terminal history buffer for a query",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["terminal_id", "query"],
        },
    ),
    Tool(
        name="add_output_alert",
        description="Register a global or session-scoped output alert pattern",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["global", "session"],
                    "description": "Alert scope",
                },
                "pattern": {"type": "string", "description": "Pattern to match in output"},
                "terminal_id": {"type": "string", "description": "Terminal ID for session alerts"},
                "label": {"type": "string", "description": "Optional label for the alert"},
            },
            "required": ["scope", "pattern"],
        },
    ),
    Tool(
        name="list_output_alerts",
        description="List registered output alert patterns",
        inputSchema={
            "type": "object",
            "properties": {
                "scope": {"type": "string", "enum": ["global", "session"], "description": "Optional scope filter"},
                "terminal_id": {"type": "string", "description": "Optional terminal filter"},
            },
        },
    ),
    Tool(
        name="remove_output_alert",
        description="Remove an output alert pattern",
        inputSchema={
            "type": "object",
            "properties": {
                "alert_id": {"type": "string", "description": "Alert ID"}
            },
            "required": ["alert_id"],
        },
    ),
    Tool(
        name="list_alert_events",
        description="List output alert matches that have fired",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Optional terminal filter"},
                "since": {"type": "integer", "description": "Only return events after this id", "default": 0},
            },
        },
    ),
    Tool(
        name="health_report",
        description="Get a health summary for sessions, alerts, and persistence",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="create_workspace",
        description="Create a workspace profile",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace ID"},
                "env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Workspace environment variables",
                },
                "startup_commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Workspace startup commands",
                },
            },
            "required": ["workspace_id"],
        },
    ),
    Tool(
        name="list_workspaces",
        description="List workspace profiles",
        inputSchema={"type": "object", "properties": {}},
    ),
    Tool(
        name="workspace_status",
        description="Get a workspace profile and its members",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace ID"}
            },
            "required": ["workspace_id"],
        },
    ),
    Tool(
        name="configure_workspace",
        description="Update a workspace profile and optionally apply it to live members",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace ID"},
                "set_env": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Environment variables to add or update",
                },
                "unset_env": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Environment variable names to remove",
                },
                "startup_commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Replace workspace startup commands",
                },
                "apply_to_members": {
                    "type": "boolean",
                    "description": "Apply the updated workspace profile to live member terminals",
                    "default": True,
                },
            },
            "required": ["workspace_id"],
        },
    ),
    Tool(
        name="add_terminal_to_workspace",
        description="Add a terminal to a workspace and apply the workspace profile",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace ID"},
                "terminal_id": {"type": "string", "description": "Terminal ID"},
            },
            "required": ["workspace_id", "terminal_id"],
        },
    ),
    Tool(
        name="remove_terminal_from_workspace",
        description="Remove a terminal from a workspace",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace ID"},
                "terminal_id": {"type": "string", "description": "Terminal ID"},
            },
            "required": ["workspace_id", "terminal_id"],
        },
    ),
    Tool(
        name="apply_workspace",
        description="Apply a workspace profile to its member terminals or one terminal",
        inputSchema={
            "type": "object",
            "properties": {
                "workspace_id": {"type": "string", "description": "Workspace ID"},
                "terminal_id": {"type": "string", "description": "Optional terminal ID"},
            },
            "required": ["workspace_id"],
        },
    ),
    Tool(
        name="add_checkpoint",
        description="Mark a named checkpoint at a cursor position",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"},
                "label": {"type": "string", "description": "Checkpoint label"},
                "note": {"type": "string", "description": "Optional note"},
                "cursor": {"type": "integer", "description": "Optional cursor position"},
            },
            "required": ["terminal_id", "label"],
        },
    ),
    Tool(
        name="list_checkpoints",
        description="List named checkpoints for all terminals or one terminal",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Optional terminal filter"}
            },
        },
    ),
    Tool(
        name="remove_checkpoint",
        description="Remove a checkpoint",
        inputSchema={
            "type": "object",
            "properties": {
                "checkpoint_id": {"type": "string", "description": "Checkpoint ID"}
            },
            "required": ["checkpoint_id"],
        },
    ),
    Tool(
        name="export_session",
        description="Export a terminal session bundle for snapshot or handoff",
        inputSchema={
            "type": "object",
            "properties": {
                "terminal_id": {"type": "string", "description": "Terminal ID"}
            },
            "required": ["terminal_id"],
        },
    ),
    Tool(
        name="import_session",
        description="Import a terminal session bundle and restore it into a live session",
        inputSchema={
            "type": "object",
            "properties": {
                "snapshot": {"type": "object", "description": "Exported session bundle"},
                "terminal_id": {"type": "string", "description": "Optional new terminal ID"},
            },
            "required": ["snapshot"],
        },
    ),
    Tool(
        name="web_url",
        description="Get the web UI URL where terminal sessions can be viewed in a browser",
        inputSchema={"type": "object", "properties": {}},
    ),
]
