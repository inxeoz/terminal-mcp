# Multi-Terminal MCP Server

MCP server that enables AI agents to manage multiple persistent terminal sessions concurrently.

## Features

- Persistent PTY-backed bash shells
- 9 MCP tools for full terminal lifecycle management
- Concurrent terminals with isolated async background readers
- Incremental cursor-based output reads
- Pattern-based output waiting
- Signal support (SIGINT, SIGTERM, SIGKILL)

## Install

```bash
uv tool install terminal-mcp
# or
pip install terminal-mcp
# or from source
uv pip install -e .
```

## Usage

With OpenCode, add to `opencode.json`:

```json
{
  "mcp": {
    "terminal": {
      "type": "local",
      "command": ["uv", "x", "terminal-mcp"],
      "enabled": true
    }
  }
}
```

Or directly:

```bash
terminal-mcp
```

## Tools

| Tool | Description |
|---|---|
| `create_terminal` | Spawn a persistent bash shell |
| `list_terminals` | List all active sessions |
| `terminal_status` | Get PID, CWD, alive, timestamps |
| `send_input` | Write text/commands to stdin |
| `read_output` | Incremental read via cursor |
| `send_signal` | Send SIGINT/SIGTERM/SIGKILL |
| `kill_terminal` | Destroy session and free resources |
| `wait_for_output` | Block until pattern appears |
| `search_output` | Search output history buffer |

## Requirements

- Python 3.11+
- Linux or macOS (pexpect PTY support)
