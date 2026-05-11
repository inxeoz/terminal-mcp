# i4z-terminal-mcp

MCP server for persistent interactive terminal sessions with a browser UI.

## Features

- Persistent PTY-backed bash shells
- Concurrent terminal sessions
- Incremental output reads
- History log for input/output events
- Searchable output history
- Session env profiles and startup hooks
- Workspace profiles and groups
- Output alerts with global/session patterns
- Health summary for sessions, alerts, and persistence
- Session checkpoints and export/import bundles
- Frontend panels for profiles, workspaces, alerts, checkpoints, and snapshots
- Create/delete sessions from the web UI
- Dark/light theme toggle

## Requirements

- Python 3.11+
- Linux or macOS

## Install

From PyPI:

```bash
pip install i4z-terminal-mcp
```

From source:

```bash
pip install -e .
```

## Build

Build a distributable wheel/sdist from source:

```bash
uv build
# or
python -m build
```

## Run

Direct:

```bash
i4z-terminal-mcp
```

Or with a fixed frontend port:

```bash
I4Z_TERMINAL_WEB_PORT=9020 i4z-terminal-mcp
```

With OpenCode:

```json
{
  "mcp": {
    "terminal": {
      "type": "local",
      "command": ["i4z-terminal-mcp"],
      "environment": {
        "I4Z_TERMINAL_WEB_PORT": "9020"
      },
      "enabled": true
    }
  }
}
```

## Frontend

The server prints the web UI URL on startup:

```bash
Web UI: http://127.0.0.1:9020
```

Open that URL in a browser to:

- create terminal sessions
- delete terminal sessions
- send commands
- view live terminal output
- filter command/history entries
- search output history
- switch between dark and light theme

If no port is configured, the server chooses a free localhost port and prints it.

## MCP tools

| Tool | Description |
|---|---|
| `create_terminal` | Create a persistent terminal session |
| `list_terminals` | List active and historical sessions |
| `terminal_status` | Get PID, cwd, alive state, timestamps |
| `terminal_profile` | Get stored env vars and startup commands |
| `configure_terminal` | Update env vars or startup hooks |
| `create_workspace` | Create a workspace profile |
| `list_workspaces` | List workspace profiles |
| `workspace_status` | Get workspace members and profile |
| `configure_workspace` | Update a workspace profile |
| `add_terminal_to_workspace` | Add a terminal to a workspace |
| `remove_terminal_from_workspace` | Remove a terminal from a workspace |
| `apply_workspace` | Apply a workspace profile to terminals |
| `send_input` | Send text/commands to stdin |
| `read_output` | Read incremental PTY output |
| `send_signal` | Send SIGINT, SIGTERM, or SIGKILL |
| `kill_terminal` | Destroy a session |
| `wait_for_output` | Wait for a substring in output |
| `search_output` | Search terminal output history |
| `add_output_alert` | Register a global or session alert pattern |
| `list_output_alerts` | List registered alert patterns |
| `remove_output_alert` | Remove an alert pattern |
| `list_alert_events` | List alert matches that fired |
| `health_report` | Get session, alert, and DB health |
| `add_checkpoint` | Mark a named checkpoint |
| `list_checkpoints` | List checkpoints |
| `remove_checkpoint` | Remove a checkpoint |
| `export_session` | Export a session bundle |
| `import_session` | Restore a session bundle |
| `web_url` | Get the frontend URL |

## Usage notes

- `send_input` accepts commands with or without a trailing newline.
- Terminal names must be at least 1 character and cannot be empty.
- Dead sessions remain visible in the UI if they have history.
- `create_terminal` accepts optional `env` and `startup_commands` fields.
- `configure_terminal` can add/remove env vars on a live session.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `I4Z_TERMINAL_WEB_PORT` | random free port | Web UI listen port |
| `I4Z_TERMINAL_STATE_DIR` | `~/.local/share/i4z-terminal-mcp` | SQLite history directory |

## License

MIT
