# i4z-terminal-mcp

MCP server for persistent interactive terminal sessions with a browser UI.

## Features

- Persistent PTY-backed bash shells
- Concurrent terminal sessions
- Incremental output reads
- History log for input/output events
- Searchable output history
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
| `send_input` | Send text/commands to stdin |
| `read_output` | Read incremental PTY output |
| `send_signal` | Send SIGINT, SIGTERM, or SIGKILL |
| `kill_terminal` | Destroy a session |
| `wait_for_output` | Wait for a substring in output |
| `search_output` | Search terminal output history |
| `web_url` | Get the frontend URL |

## Usage notes

- `send_input` accepts commands with or without a trailing newline.
- Terminal names must be at least 1 character and cannot be empty.
- Dead sessions remain visible in the UI if they have history.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `I4Z_TERMINAL_WEB_PORT` | random free port | Web UI listen port |
| `I4Z_TERMINAL_STATE_DIR` | `~/.local/share/i4z-terminal-mcp` | SQLite history directory |

## License

MIT
