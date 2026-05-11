# i4z-terminal-mcp — Specification

**Version**: 0.6.0  
**Language**: Python 3.11+  
**Runtime**: asyncio  
**Dependencies**: `mcp`, `pexpect`, `starlette`, `uvicorn` (transitive via `mcp`)  
**License**: MIT

---

## Overview

i4z-terminal-mcp is an MCP (Model Context Protocol) server that provides AI agents with persistent, concurrent terminal sessions. Each terminal is a real `/bin/bash` shell backed by a PTY via `pexpect`. An embedded web UI built with xterm.js allows humans to view and interact with the same terminals in a browser.

---

## Architecture

```
AI Agent (OpenCode, MCP Inspector, etc.)
    │  MCP stdio (JSON-RPC)
    ▼
┌─────────────────────────────────────┐
│ i4z-terminal-mcp                    │
│                                     │
│  ┌─ MCP Server ───────────────────┐ │
│  │  10 tools exposed to AI        │ │
│  │  stdio transport               │ │
│  └────────────────────────────────┘ │
│                                     │
│  ┌─ SessionManager ───────────────┐ │
│  │  TerminalSession registry      │ │
│  │  HistoryStore adapter          │ │
│  │  Output buffer (cursor model)  │ │
│  └────────────────────────────────┘ │
│                                     │
│  ┌─ Terminal Sessions ────────────┐ │
│  │  session-a: PTY /bin/bash      │ │
│  │  session-b: PTY /bin/bash      │ │
│  │  ...                            │ │
│  │  Each: reader_loop (asyncio)   │ │
│  └────────────────────────────────┘ │
│                                     │
│  ┌─ Web Server (starlette) ───────┐ │
│  │  :9020 (or random free port)   │ │
│  │  6 REST endpoints              │ │
│  │  xterm.js UI                   │ │
│  └────────────────────────────────┘ │
└─────────────────────────────────────┘
```

---

## Project Structure

```
i4z-terminal-mcp/
├── terminal/
│   ├── __init__.py
│   ├── server.py       # MCP server entry point, CLI main()
│   ├── tools.py        # 10 MCP tool definitions (JSON Schema)
│   ├── manager.py      # SessionManager: lifecycle, delegation
│   ├── history.py      # HistoryStore: SQLite events/history/search
│   ├── session.py      # TerminalSession: PTY shell, output buffer, cursor
│   ├── reader.py       # Background asyncio reader loop (50ms poll)
│   ├── signals.py      # SIGINT/SIGTERM/SIGKILL dispatch
│   ├── web.py          # Starlette web server, HTML UI, REST endpoints
│   └── log.py          # Structured stderr logger (timestamps + prefixes)
├── pyproject.toml      # Package metadata, console_scripts entry point
├── requirements.txt
├── opencode.json       # Example OpenCode MCP config
├── README.md
└── .gitignore
```

---

## MCP Tools (10)

### `create_terminal`
Spawn a persistent PTY-backed `/bin/bash` session.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | yes | Unique terminal identifier |

Returns: `{"terminal_id": "...", "status": "created"}`

### `list_terminals`
Enumerate all active terminal sessions.
No parameters.

Returns: `[{"id": "...", "alive": true}, ...]`

### `terminal_status`
Get runtime metadata for a terminal.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `terminal_id` | string | yes | Terminal ID |

Returns: `{"id": "...", "alive": true, "pid": 12345, "cwd": "/project", "created_at": "...", "last_activity": "..."}`

### `send_input`
Write text/commands to the PTY stdin. Include `\n` to execute.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `terminal_id` | string | yes | Terminal ID |
| `text` | string | yes | Text to send (e.g., `"npm run dev\n"`) |

Returns: `{"status": "sent"}`

### `read_output`
Read raw PTY output since a cursor position (incremental, not full history).
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `terminal_id` | string | yes | | Terminal ID |
| `since` | integer | no | 0 | Byte cursor offset |
| `max_bytes` | integer | no | | Cap on returned bytes |

Returns: `{"output": "...", "cursor": 1298}`

### `send_signal`
Send a POSIX signal to the terminal's process group.
| Parameter | Type | Required | Values |
|-----------|------|----------|--------|
| `terminal_id` | string | yes | |
| `signal` | string | yes | `SIGINT`, `SIGTERM`, `SIGKILL` |

Returns: `{"status": "signaled"}`

### `kill_terminal`
Destroy a terminal session — cancel reader task, terminate PTY, free resources.
| Parameter | Type | Required |
|-----------|------|----------|
| `terminal_id` | string | yes |

Returns: `{"status": "killed"}`

### `wait_for_output`
Block until a pattern appears in terminal output (poll-based, 100ms interval).
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `terminal_id` | string | yes | | Terminal ID |
| `pattern` | string | yes | | Substring to match |
| `timeout` | number | no | 30 | Max wait in seconds |

Returns: `{"matched": true/false, "cursor": 2044}`

### `search_output`
Search the raw PTY output buffer for a query (case-insensitive).
| Parameter | Type | Required |
|-----------|------|----------|
| `terminal_id` | string | yes |
| `query` | string | yes |

Returns: `{"matches": ["line containing query", ...]}`

### `web_url`
Return the web UI URL for the current server instance.
No parameters.

Returns: `{"url": "http://127.0.0.1:9020"}`

---

## Web UI

The embedded Starlette server serves a single-page app at the port configured via `I4Z_TERMINAL_WEB_PORT` (default: random free port).

### REST Endpoints (6)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | xterm.js + history HTML UI |
| `GET` | `/api/terminals` | JSON list of all terminals |
| `GET` | `/api/status/{id}` | JSON: PID, alive, CWD, timestamps |
| `GET` | `/api/output/{id}?since=N` | Raw PTY output (cursor-based, for xterm.js) |
| `GET` | `/api/history/{id}?since=N` | Clean ANSI-stripped input/output events from SQLite |
| `POST` | `/api/send/{id}` | `{"text": "command\n"}` — execute in terminal |

### Frontend Layout

```
┌──────────┬────────────────────────────┐
│ Sidebar  │  Toolbar (PID, CWD, alive) │
│ terminal ├────────────────────────────│
│ list     │                            │
│          │  xterm.js (interactive)    │
│ ● demo   │  ← type commands directly │
│ ● build  │    ANSI colors rendered    │
│          │    term.onData() → POST    │
│          ├───────────┬────────────────│
│          │  History  │  12:34 IN ls   │
│          │  panel    │  12:34 OUT ... │
│          │  (resize) │                │
└──────────┴───────────┴────────────────┘
```

- **xterm.js** (v5 via CDN importmap): renders raw PTY output with full ANSI support. Polls `GET /api/output/{id}` every 150ms. Keystrokes captured via `term.onData()` and sent to `POST /api/send/{id}`.
- **History panel**: clean input/output log from SQLite (ANSI-stripped). Polls `GET /api/history/{id}` every 1s.
- **Draggable grip**: resize terminal vs history panel vertically.
- **Sidebar**: terminal list with green/red status dots, auto-refreshes every 2s.

---

## Data Model

### In-Memory (per session)

```python
output_buffer: deque(maxlen=5000)  # entries: (cursor_offset, text)
cursor: int                         # monotonic bytes-written counter
```

Used for `read_output` and `GET /api/output` — fast, bounded, cursor-based incremental reads.

### SQLite (per process)

```sql
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('input','output')),
    text TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX idx_events_terminal ON events(terminal_id, id);
```

- File path: `~/.local/share/i4z-terminal-mcp/sessions-{pid}.db`
- Override: set `I4Z_TERMINAL_STATE_DIR` env var for custom directory
- Each process gets its own DB (pid in filename) — no cross-contamination
- ANSI escape sequences stripped before writing to DB
- Input events recorded on `send_input` / `POST /api/send`
- Output events recorded via `on_output` callback from reader loop
- Used for history panel in web UI and `search_output` tool

---

## Concurrency Model

- One `asyncio.Task` per terminal session (background reader loop)
- Reader polls PTY via `shell.read_nonblocking(size=4096, timeout=0)` every 50ms
- MCP server and web server run concurrently via `asyncio.gather`
- Input recorded synchronously; output captured asynchronously by reader
- Scale target: 2–20 concurrent terminals on localhost

---

## Terminal Lifecycle

```
create → spawn PTY → start reader → register session
       ↓
send_input → PTY stdin → shell executes → reader captures → buffer + SQLite
       ↓
kill_terminal → cancel reader → terminate PTY → close DB entry → free
```

Dead shells are detected via `shell.isalive()` and marked dead by the reader loop. Buffered logs are preserved in SQLite after death.

---

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `I4Z_TERMINAL_WEB_PORT` | random free port | Web UI listen port |
| `I4Z_TERMINAL_STATE_DIR` | `~/.local/share/i4z-terminal-mcp` | SQLite storage directory |

---

## Install & Usage

```bash
# From PyPI
uv tool install i4z-terminal-mcp

# From GitHub
uvx --from git+https://github.com/inxeoz/terminal-mcp i4z-terminal-mcp

# From source
uv pip install -e .
```

### With OpenCode

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

### Direct

```bash
i4z-terminal-mcp                     # random port
I4Z_TERMINAL_WEB_PORT=8080 i4z-terminal-mcp  # fixed port
```

### Manual SQLite Inspection

```bash
sqlite3 ~/.local/share/i4z-terminal-mcp/sessions-<pid>.db "SELECT * FROM events"
sqlite3 ~/.local/share/i4z-terminal-mcp/sessions-<pid>.db ".schema"
```

---

## Logging

Structured stderr output with UTC timestamps and source prefixes:

```
18:47:30  [DB]    SQLite: /home/inxeoz/.local/share/.../sessions-370636.db
18:47:30  [MCP]   create_terminal(name='test')
18:47:30  [TERM]  terminal 'test' created, pid=370683
18:47:30  [MCP]   -> terminal_id=test
18:47:30  [TERM]  reader started for 'test'
18:47:30  [MCP]   send_input(terminal_id='test', text='ls\n')
18:47:30  [TERM]  'test' <- ls
18:47:30  [WEB]   GET /api/terminals
18:47:30  [WEB]   POST /api/send/test 'echo hello'
```

Tags: `[MCP]` = tool calls, `[TERM]` = terminal lifecycle, `[WEB]` = HTTP requests, `[DB]` = SQLite path.

---

## Security

Localhost-only. Provides unrestricted shell access. Do not expose externally. No authentication.
