# i4z-terminal-mcp — Specification

**Version**: 1.0.0  
**Languages**: Python 3.11+ (reference) · Rust (production)  
**Runtimes**: asyncio (Python) · tokio (Rust)  
**License**: MIT

---

## Overview

i4z-terminal-mcp is an MCP (Model Context Protocol) server that provides AI agents with persistent, concurrent terminal sessions. Each terminal is a real `/bin/bash` shell backed by a PTY. An embedded web UI built with xterm.js allows humans to view and interact with the same terminals in a browser.

**Dual implementation**: Python reference implementation (asyncio + pexpect + Starlette) and Rust production port (tokio + pty-process + actix-web). Both share identical MCP protocol, HTTP API, and WebSocket protocol.

---

## Architecture

```
            AI Agent (OpenCode, MCP Inspector, etc.)
                │  MCP stdio (JSON-RPC)
                ▼
┌──────────────────────────────────────────────────┐
│ i4z-terminal-mcp                                 │
│                                                  │
│  ┌─ MCP Server ────────────────────────────────┐ │
│  │  34 tools exposed to AI                     │ │
│  │  Python: mcp SDK  ·  Rust: rmcp (proc-macro)│ │
│  │  stdio transport                            │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌─ Manager ───────────────────────────────────┐ │
│  │  Python: SessionManager (dict)              │ │
│  │  Rust:   Manager (DashMap)                  │ │
│  │  Terminal lifecycle                         │ │
│  │  Profiles, workspaces, alerts, checkpoints  │ │
│  │  Export/import, health reports              │ │
│  │  Output buffer (cursor model)               │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌─ History ───────────────────────────────────┐ │
│  │  Python: HistoryStore (sqlite3, sync)       │ │
│  │  Rust:   History (SQLx, async)              │ │
│  │  8 SQLite tables                            │ │
│  │  ANSI stripping before write                │ │
│  │  UUID-based alert/checkpoint IDs            │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌─ Terminal Sessions ─────────────────────────┐ │
│  │  Python: pexpect.spawn + asyncio reader     │ │
│  │  Rust:   pty-process + tokio task           │ │
│  │  session-a: PTY /bin/bash                   │ │
│  │  session-b: PTY /bin/bash                   │ │
│  │  Each: background reader loop               │ │
│  └─────────────────────────────────────────────┘ │
│                                                  │
│  ┌─ Web Server ────────────────────────────────┐ │
│  │  Python: Starlette + uvicorn                │ │
│  │  Rust:   actix-web + actix-ws               │ │
│  │  :random (or I4Z_TERMINAL_WEB_PORT)         │ │
│  │  25 REST endpoint types                     │ │
│  │  WebSocket (JSON protocol)                  │ │
│  │  xterm.js UI (inlined/embedded)             │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

---

## Project Structure

```
i4z-terminal-mcp/
├── Cargo.toml                 # Cargo workspace root
├── Cargo.lock
├── Makefile                   # Build/run/test targets
├── README.md                  # Project overview
├── spec.md                    # This file
├── HANDOFF.md
│
├── crates/
│   ├── server/                # Rust MCP server
│   │   ├── Cargo.toml
│   │   ├── src/
│   │   │   ├── main.rs        # Entry point: web + MCP + signal handling
│   │   │   ├── lib.rs         # Module exports
│   │   │   ├── tools.rs       # 34 MCP tools via rmcp proc-macro
│   │   │   ├── manager.rs     # Manager: session lifecycle, I/O, alerts, workspaces
│   │   │   ├── history.rs     # History: SQLx async SQLite
│   │   │   ├── session.rs     # Session: PTY wrapper, bounded deque buffer, CWD
│   │   │   ├── web.rs         # actix-web server: 25 REST + WS + HTML/egui UI
│   │   │   ├── error.rs       # Error types
│   │   │   └── bin/
│   │   │       ├── bench.rs   # Performance benchmark
│   │   │       └── stress.rs  # Stress test (20 concurrent sessions)
│   │   ├── tests/
│   │   │   └── parity.rs
│   │   ├── migrations/        # SQL migration files
│   │   └── index.html         # HTML frontend fallback (embedded at compile)
│   │
│   └── frontend/              # egui WASM UI (trunk build)
│       ├── Cargo.toml
│       ├── index.html
│       └── src/
│           └── main.rs        # egui app: terminal list, output, input, WS
│
├── test.mjs                   # Web integration tests
├── test.md
└── .gitignore
```

---

## Implementation Comparison

| | Python | Rust |
|---|---|---|
| Language | Python 3.11+ | Rust (edition 2021) |
| Runtime | asyncio event loop | tokio multi-threaded |
| PTY | pexpect (sync) | pty-process + libc (async) |
| MCP SDK | mcp (mcp Python SDK) | rmcp 0.11 (proc-macro) |
| Web server | Starlette + uvicorn | actix-web 4 + actix-ws |
| Database | sqlite3 (sync, threaded) | SQLx 0.8 (async, pooled) |
| Sessions | dict (single-threaded) | DashMap (lock-free concurrent) |
| Output buffer | collections.deque(maxlen=5000) | VecDeque bounded |
| ANSI strip | re.sub | regex Regex replace |
| IDs | uuid.uuid4().hex | uuid::Uuid::new_v4().to_hex() |
| Frontend | Python string constant | include_str! at compile time |
| Logging | custom stderr logger | tracing + tracing-subscriber |
| Binary size | ~2MB (interpreted) | ~15MB (compiled) |
| Startup time | ~200ms (import overhead) | ~3ms (native) |
| Command throughput | ~2k cmd/s | ~9k cmd/s |
| Concurrent sessions | 20 (tested) | 20 (tested) |

---

## MCP Tools (34)

### `create_terminal`
Spawn a persistent PTY-backed `/bin/bash` session.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | yes | Unique terminal identifier |
| `env` | object | no | Environment variables |
| `startup_commands` | array | no | Commands to run after shell starts |
| `workspace_id` | string | no | Workspace preset to seed from |

Returns: `{"terminal_id": "...", "status": "created"}`

### `list_terminals`
Enumerate all terminal sessions (active + dead from history).
No parameters.

Returns: `[{"id": "...", "alive": true}, ...]`

### `terminal_status`
Get runtime metadata for a terminal (falls back to history for dead terminals).
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `terminal_id` | string | yes | Terminal ID |

Returns: `{"id": "...", "alive": true, "pid": 12345, "cwd": "/project", "created_at": "...", "last_activity": "...", "reader_error": null, "profile": {...}, "workspaces": [...]}`

### `terminal_profile`
Get stored env vars and startup commands for a terminal.

### `configure_terminal`
Update env vars (sends `export`/`unset` to live shell), startup commands, or both.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `terminal_id` | string | yes | Terminal ID |
| `set_env` | object | no | Env vars to set |
| `unset_env` | array | no | Env var names to unset |
| `startup_commands` | array | no | Replace startup commands |
| `run_startup_commands` | boolean | no | Run immediately |

### `create_workspace`
Create a workspace profile with shared env + startup commands.

### `list_workspaces`
List workspace profiles with member counts.

### `workspace_status`
Get a workspace profile and its members.

### `configure_workspace`
Update a workspace profile and optionally apply it to live member terminals.

### `add_terminal_to_workspace`
Add a terminal to a workspace and apply the workspace profile.

### `remove_terminal_from_workspace`
Remove a terminal from a workspace.

### `apply_workspace`
Apply a workspace profile to its member terminals or one specific terminal.

### `send_input`
Write text/commands to the PTY stdin. Auto-appends `\n` if missing.
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
Destroy a terminal session — terminate PTY, await reader task, free resources.
| Parameter | Type | Required |
|-----------|------|----------|
| `terminal_id` | string | yes |

Returns: `{"status": "killed"}`

### `wait_for_output`
Block until a substring appears in terminal output (Notify-based, sub-100ms latency).
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `terminal_id` | string | yes | | Terminal ID |
| `pattern` | string | yes | | Substring to match |
| `timeout` | number | no | 30 | Max wait in seconds |

Returns: `{"matched": true/false, "cursor": 2044}`

### `search_output`
Search output buffer (live) or history DB (dead) for a query (case-insensitive).
| Parameter | Type | Required |
|-----------|------|----------|
| `terminal_id` | string | yes |
| `query` | string | yes |

Returns: `{"matches": ["line containing query", ...]}`

### `add_output_alert`
Register a global or session-scoped output alert pattern.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `scope` | string | yes | `global` or `session` |
| `pattern` | string | yes | Pattern to match in output |
| `terminal_id` | string | no | Required for session scope |
| `label` | string | no | Optional label |

Returns: `{"id": "hex-uuid", "scope": "...", "pattern": "...", "terminal_id": "...", "label": "..."}`

### `list_output_alerts`
List registered output alert patterns (optional scope/terminal_id filters).

### `remove_output_alert`
Remove an alert pattern by UUID.
| Parameter | Type | Required |
|-----------|------|----------|
| `alert_id` | string | yes |

Returns: `{"removed": true, "alert_id": "..."}`

### `list_alert_events`
List alert matches that have fired (optional since + terminal_id filters).

### `health_report`
Get a health summary: DB status, event counts, session counts, reader errors, stale sessions.

### `add_checkpoint`
Mark a named checkpoint at a cursor position in output history.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `terminal_id` | string | yes | Terminal ID |
| `label` | string | yes | Checkpoint label |
| `note` | string | no | Optional note |
| `cursor` | integer | no | Cursor position (default: current) |

Returns: `{"id": "hex-uuid", "terminal_id": "...", "label": "...", "cursor": N, "note": "..."}`

### `list_checkpoints`
List checkpoints for one terminal or all terminals.

### `remove_checkpoint`
Remove a checkpoint by UUID.

### `export_session`
Export a session bundle: profile, history events, alerts, checkpoints, workspace memberships, status.
| Parameter | Type | Required |
|-----------|------|----------|
| `terminal_id` | string | yes |

Returns: `{"terminal_id": "...", "profile": {...}, "history": {...}, "alerts": [...], "checkpoints": [...], "workspaces": [...], "workspace_profiles": [...], "status": {...}}`

### `import_session`
Restore a session from a bundle — creates terminal, replays input events, restores alerts, checkpoints, and workspace memberships.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `snapshot` | object | yes | Exported session bundle |
| `terminal_id` | string | no | Target terminal ID (default: source ID) |

Returns: `{"terminal_id": "...", "status": "imported"}`

### `web_url`
Return the web UI URL for the current server instance.
No parameters.

Returns: `{"url": "http://localhost:9020"}`

### `rename_terminal`
Rename a terminal — updates in-memory session, all 7 SQLite tables (events, profiles, alerts, alert_events, bookmarks, workspace_members, reader_errors), and workspace memberships.
| Parameter | Type | Required |
|-----------|------|----------|
| `terminal_id` | string | yes |
| `new_id` | string | yes |

Returns: `{"old_id": "...", "new_id": "..."}`

### `resize_terminal`
Set PTY dimensions (rows × cols) via `ioctl(TIOCSWINSZ)`.
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `terminal_id` | string | yes | Terminal ID |
| `rows` | integer | yes | Number of rows (≥1) |
| `cols` | integer | yes | Number of columns (≥1) |

Returns: `{"status": "resized", "terminal_id": "...", "rows": N, "cols": N}`

---

## Web UI

The embedded web server serves a single-page app at the port configured via `I4Z_TERMINAL_WEB_PORT` (default: random free port).

### REST Endpoints (25 route patterns)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | xterm.js + history HTML UI |
| `GET` | `/api/terminals` | JSON list of all terminals (active + dead) |
| `POST` | `/api/create` | Create a terminal session |
| `GET` | `/api/status/{id}` | JSON: PID, alive, CWD, timestamps, profile, workspaces |
| `GET` | `/api/profile/{id}` | Session env vars and startup commands |
| `POST` | `/api/profile/{id}` | Update session env/startup (sends commands to live shell) |
| `POST` | `/api/send/{id}` | `{"text": "command\n"}` — execute in terminal |
| `POST` | `/api/kill/{id}` | Destroy a terminal session |
| `POST` | `/api/rename/{id}` | Rename a terminal |
| `POST` | `/api/resize/{id}` | Set PTY dimensions |
| `POST` | `/api/signal/{id}` | Send POSIX signal |
| `GET` | `/api/history/{id}?since=N` | Clean ANSI-stripped input/output events from SQLite |
| `GET` | `/api/search/{id}?query=X` | Search output history |
| `GET` | `/api/health` | Health summary |
| `GET` | `/api/workspaces` | List workspace profiles |
| `POST` | `/api/workspaces` | Create a workspace |
| `GET` | `/api/workspaces/{ws_id}` | Workspace profile + members |
| `POST` | `/api/workspaces/{ws_id}` | Update workspace env/startup |
| `POST` | `/api/workspaces/{ws_id}/members` | Add terminal to workspace |
| `DELETE` | `/api/workspaces/{ws_id}/members/{tid}` | Remove terminal from workspace |
| `POST` | `/api/workspaces/{ws_id}/apply` | Apply workspace to members |
| `GET` | `/api/alerts` | List alerts (optional scope/terminal_id filters) |
| `POST` | `/api/alerts` | Create an alert |
| `DELETE` | `/api/alerts/{id}` | Remove an alert |
| `GET` | `/api/alert-events` | List alert matches (optional since/terminal_id) |
| `GET` | `/api/checkpoints` | List checkpoints (optional terminal_id filter) |
| `POST` | `/api/checkpoints` | Create a checkpoint |
| `DELETE` | `/api/checkpoints/{id}` | Remove a checkpoint |
| `GET` | `/api/export/{id}` | Export a session bundle |
| `POST` | `/api/import` | Import a session bundle |
| `WS` | `/ws/{id}?since=N` | WebSocket: initial history + live output stream |

### WebSocket Protocol

Connects with optional `?since=N` query param for initial history offset. Server sends:

1. `{"type": "history", "events": [...], "cursor": N}` — initial history replay
2. `{"type": "status", "status": {...}}` — current terminal status
3. `{"type": "output", "text": "...", "cursor": N}` — streaming output

Client sends:
- `{"type": "input", "text": "..."}` — write to PTY stdin
- `{"type": "resize", "rows": N, "cols": N}` — resize PTY

### Frontend Layout

```
┌──────────┬────────────────────────────────────────────┐
│ Sidebar  │  Tabs (terminal A | terminal B | ×)        │
│ terminal ├────────────────────────────────────────────│
│ list     │                                            │
│          │  xterm.js (interactive)                    │
│ ● demo   │  ← type commands directly                  │
│ ● build  │    ANSI colors rendered                    │
│          │    term.onData() → WebSocket JSON           │
│          ├────────────────────────────────────────────│
│          │  Command bar: $ input | Ctrl+C | Clear      │
│          └───────────┬────────────────────────────────│
│          │  Right     │  Profile / Workspace / Alerts   │
│          │  Panel     │  Checkpoints / Snapshots        │
│          │  (toggle)  │                                 │
└──────────┴───────────┴────────────────────────────────┘
```

- **xterm.js** (v5 via CDN): renders raw PTY output with full ANSI support
- **WebSocket**: polls `GET /api/history/{id}` for initial load, then streams output via WS
- **History panel**: clean input/output log from SQLite (ANSI-stripped)
- **Management panels**: session profile, workspace, alert, checkpoint, and snapshot panels
- **Draggable grips**: resize sidebar and right panel
- **Tab system**: multiple terminals open at once, side-by-side split view
- **Dark/light theme** with localStorage persistence
- **Responsive**: mobile/tablet drawer-based layout

---

## Data Model

### In-Memory (per session)

```
output_buffer: bounded deque (max 5000 entries)
  entry = (cursor_offset: usize, text: String)
cursor: usize  — monotonic bytes-written counter
```

Used for `read_output` and `GET /api/output` — fast, bounded, cursor-based incremental reads. Entries older than the 5000 bound are dropped from the front.

### SQLite (per process)

```
events           — input/output history (ANSI-stripped on write)
session_profiles — env JSON + startup commands per terminal
alerts           — output alert patterns (UUID primary key)
alert_events     — fired alert matches
reader_errors    — per-terminal reader error messages
bookmarks        — named cursor checkpoints (UUID primary key)
workspaces       — workspace profiles (env + startup)
workspace_members — workspace ↔ terminal membership
```

- **Python**: `~/.local/share/i4z-terminal-mcp/sessions-{pid}.db`
- **Rust**: `~/.local/share/i4z-terminal-mcp/history.db`
- Override: set `I4Z_TERMINAL_STATE_DIR` env var for custom directory
- Python: per-process DB (pid in filename) — no cross-contamination
- Rust: shared DB file — idempotent via `CREATE TABLE IF NOT EXISTS`
- ANSI escape sequences stripped before writing to DB
- Input recorded on `send_input`; Output recorded by background reader
- Alert and checkpoint IDs are hex UUIDs (no hyphens)

---

## Concurrency Model

| | Python | Rust |
|---|---|---|
| Reader per session | `asyncio.Task` | `tokio::task` |
| Poll interval | 50ms `read_nonblocking` | Event-driven `AsyncReadExt::read` |
| Server concurrency | `asyncio.gather(MCP, web)` | `tokio::spawn(MCP)` + `tokio::select!(web, signal)` |
| Session registry | `dict` (single-threaded) | `DashMap` (lock-free concurrent) |
| Input recording | Synchronous | Async (channel → pty_task) |
| Output capture | Async via reader | Async via reader |
| Scale target | 2–20 concurrent terminals | 2–20 concurrent terminals |

---

## Terminal Lifecycle

```
create → validate name → merge profile/workspace/env → spawn PTY → start reader
       → register session → send startup commands
       ↓
send_input → PTY stdin → shell executes → reader captures → output buffer + SQLite
       ↓  (also checks alert patterns on each output chunk)
       ↓
kill_terminal → mark dead → terminate PTY → cancel/await reader task → free
```

Dead shells are detected when the reader receives EOF or `child.wait()` completes. Output buffer and SQLite history are preserved after death. Dead terminals appear in `list_terminals` with `alive: false`.

---

## Environment Variable Management

Environment changes flow through three layers:

1. **Session profile** (DB) — persisted env vars + startup commands per terminal
2. **Workspace profile** (DB) — shared env + startup inherited by member terminals
3. **Runtime env** (live shell) — `export KEY=VALUE` sent to running PTY

When creating a terminal: `profile_env + workspace_env + create_call_env → spawn env`.
When configuring: `set_env` → DB update + live `export` command.
Workspace application sends `export` + startup commands to all member terminals.

Env variable names are validated: must match `^[A-Za-z_][A-Za-z0-9_]*$`.

---

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `I4Z_TERMINAL_WEB_PORT` | random free port | Web UI listen port |
| `I4Z_TERMINAL_WEB_HOST` | `0.0.0.0` | Web UI bind address |
| `I4Z_TERMINAL_STATE_DIR` | `~/.local/share/i4z-terminal-mcp` | SQLite storage directory |

---

## Install & Usage

### Rust

```bash
cargo build --release -p i4z-terminal-mcp
./target/release/i4z-terminal-mcp         # random port
I4Z_TERMINAL_WEB_PORT=8080 cargo run --release -p i4z-terminal-mcp
```

### Makefile (from project root)

```bash
make rs-build        # cargo build (debug)
make rs-run          # cargo run (debug)
make test            # cargo test
make bench           # Rust benchmark
make stress          # Rust stress test (20 sessions)
make inspect-rust    # MCP Inspector (Rust, local binary)
make clean           # clean build artifacts
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

For Rust: replace `"command": ["i4z-terminal-mcp"]` with path to the compiled binary.

---

## Logging

### Python

Structured stderr output with UTC timestamps and source prefixes:

```
18:47:30  [DB]    SQLite: /home/inxeoz/.local/share/.../sessions-370636.db
18:47:30  [MCP]   create_terminal(name='test')
18:47:30  [TERM]  terminal 'test' created, pid=370683
18:47:30  [WEB]   GET /api/terminals
```

Tags: `[MCP]` = tool calls, `[TERM]` = terminal lifecycle, `[WEB]` = HTTP requests, `[DB]` = SQLite path, `[ALERT]` = alert matches.

### Rust

Structured tracing output via `tracing-subscriber` with env-filter support:

```
INFO i4z_terminal_mcp: terminal 'test' created, pid=370683
INFO i4z_terminal_mcp: reader started for 'test'
```

Set `RUST_LOG=debug` for verbose output, `RUST_LOG=warn` to suppress info.

---

## Security

Localhost-only. Provides unrestricted shell access. Do not expose externally. No authentication.
