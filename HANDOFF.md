# i4z-terminal-mcp — Handoff

**Date**: 2026-05-13  
**Repo**: `inxeoz/terminal-mcp` (GitHub)  
**Head**: `798358e` (master)

---

## What this is

An MCP (Model Context Protocol) server that gives AI agents real persistent PTY terminal sessions backed by `/bin/bash`. Ships as two parallel implementations — Python (reference) and Rust (production) — both exposing the same 31 MCP tools, REST API, WebSocket protocol, and embedded web UI.

**Key property**: terminals persist between MCP calls. An agent can `create_terminal`, run a build, come back 10 minutes later, and call `read_output` to see what happened. The web UI lets a human watch the same terminals in a browser in real time.

---

## Current state — what works

- ✅ Rust binary fully functional: MCP stdio transport, web server, WebSocket
- ✅ 31 MCP tools (create/kill/delete, send/read, alerts, checkpoints, workspaces, snapshots, search)
- ✅ Web UI: 3-panel layout (sidebar / xterm.js terminal / right panel), cozy warm-stone theme
- ✅ Right panel tabs: Profile · Workspace · Alerts · Checkpoints · Search · Snapshots
- ✅ All `alert()`/`confirm()` replaced with toast notifications + `console.error` logging
- ✅ Info bar with live terminal size, kill/clear/search buttons
- ✅ Sidebar kill (⏹) vs delete (×) actions with inline confirm
- ✅ DB schema migrations handle old `kind/data/ts` columns → `type/text/timestamp`
- ✅ Playwright integration tests: **9/9 passing** (`make rs-test-web`)
- ✅ Python implementation at parity for core features

---

## Project layout

```
.
├── rust/                   ← Production implementation (Rust)
│   ├── src/
│   │   ├── main.rs         ← Entry point, port/state-dir config
│   │   ├── manager.rs      ← Terminal lifecycle, all business logic
│   │   ├── session.rs      ← PTY session (pty-process + tokio reader task)
│   │   ├── history.rs      ← SQLite persistence (sqlx async), migrations
│   │   ├── tools.rs        ← MCP tool definitions (rmcp proc-macro #[tool])
│   │   ├── web.rs          ← actix-web HTTP API + actix-ws WebSocket
│   │   └── error.rs        ← Unified Error type
│   ├── index.html          ← Entire frontend (single file, embedded at compile time)
│   └── Cargo.toml
├── python/                 ← Reference implementation (Python)
│   └── terminal/
│       ├── server.py       ← MCP + web server entrypoint
│       ├── manager.py      ← SessionManager
│       ├── history.py      ← SQLite via sqlite3 (sync)
│       ├── tools.py        ← MCP tool definitions
│       ├── session.py      ← pexpect PTY session
│       └── web.py          ← Starlette HTTP + WebSocket + embedded HTML
├── test.mjs                ← Playwright integration tests (9 tests)
├── spec.md                 ← Full protocol/architecture spec
└── Makefile                ← All build/run/test targets
```

---

## How to run

```bash
# Rust (production) — builds release binary, starts MCP+web server
make rs-run-release
# Default web port: random free port, printed on startup
# Override: I4Z_TERMINAL_WEB_PORT=9020 make rs-run-release

# Python (reference) — web-only dev mode (no MCP)
make py-run-dev          # port 9020

# Install Rust binary globally → ~/.local/bin/
make rs-install-global
```

**Environment variables**:
| Variable | Default | Description |
|---|---|---|
| `I4Z_TERMINAL_WEB_PORT` | random free port | HTTP/WebSocket port |
| `I4Z_TERMINAL_STATE_DIR` | `~/.local/share/i4z-terminal-mcp/` | SQLite DB directory |

**Claude Code / MCP config** (`~/.config/opencode/config.json` or equivalent):
```json
{
  "mcpServers": {
    "i4z-terminal-mcp": { "command": "i4z-terminal-mcp" }
  }
}
```

---

## How to test

```bash
# Run all 9 Playwright tests (starts server on 9021 with fresh tmp DB)
make rs-test-web

# Rust unit/integration tests
make test

# Run MCP Inspector against local binary
make inspect-rust

# Cargo check only (fast)
make check
```

---

## Architecture in brief

```
AI Agent ─── MCP stdio (JSON-RPC) ──► tools.rs ──► manager.rs
                                                        │
Browser ──── HTTP REST ──────────────► web.rs ──────────┤
Browser ──── WebSocket /ws/{id} ──────► web.rs ──────────┤
                                                        │
                                               session.rs (PTY)
                                               history.rs (SQLite)
```

**Data flow for terminal output:**
1. PTY reader task (tokio) reads bytes → strips ANSI → appends to in-memory ring buffer
2. Simultaneously broadcasts to all WS subscribers (tokio broadcast channel)
3. Persists to `events` table in SQLite
4. WS handler: subscribe **before** fetching history (race condition prevention), replay history, then stream live events

---

## SQLite schema (8 tables)

| Table | Purpose |
|---|---|
| `events` | All PTY output/input events (`type`, `text`, `timestamp`) |
| `session_profiles` | Per-terminal env vars + startup commands |
| `alerts` | Output pattern alerts (global or session-scoped) |
| `alert_events` | Fired alert matches with matched text |
| `reader_errors` | PTY reader task errors |
| `workspaces` | Named groups of terminals with shared env/startup |
| `workspace_members` | Terminal ↔ workspace membership |
| `checkpoints` | Named bookmarks in terminal history |

DB path: `$I4Z_TERMINAL_STATE_DIR/history.db` (defaults to `~/.local/share/i4z-terminal-mcp/history.db`)

---

## MCP tools (31)

| Category | Tools |
|---|---|
| **Terminal lifecycle** | `create_terminal`, `list_terminals`, `terminal_status`, `kill_terminal`, `delete_terminal`, `rename_terminal`, `resize_terminal` |
| **I/O** | `send_input`, `read_output`, `send_signal`, `wait_for_output`, `search_output` |
| **Profile** | `terminal_profile`, `configure_terminal` |
| **Workspaces** | `create_workspace`, `list_workspaces`, `workspace_status`, `configure_workspace`, `add_terminal_to_workspace`, `remove_terminal_from_workspace`, `apply_workspace` |
| **Alerts** | `add_output_alert`, `list_output_alerts`, `remove_output_alert`, `list_alert_events` |
| **Checkpoints** | `add_checkpoint`, `list_checkpoints`, `remove_checkpoint` |
| **Snapshots** | `export_session`, `import_session` |
| **Meta** | `health_report`, `server_info`, `web_url` |

---

## Web API (33 routes)

```
GET    /                            → embedded index.html
GET    /api/info                    → {name, version, implementation, web_url}
GET    /api/health                  → db status, session counts, error list
GET    /api/terminals               → [{id, alive, ...}]
POST   /api/create                  → {name} → {terminal_id}
DELETE /api/terminals/{id}          → delete terminal + all history
GET    /api/status/{id}             → {alive, pid, ...}
POST   /api/kill/{id}               → kill process, keep history
POST   /api/rename/{id}             → {new_id}
POST   /api/resize/{id}             → {rows, cols}
POST   /api/send/{id}               → {text}
GET    /api/history/{id}?since=N    → {events, cursor}
GET    /api/search/{id}?q=query     → {events}
POST   /api/signal/{id}             → {signal: "SIGINT"|"SIGTERM"}
GET    /api/profile/{id}            → profile object
POST   /api/profile/{id}            → {set_env, unset_env, startup_commands, run_startup_commands}
GET    /api/alerts?terminal_id=     → [alert]
POST   /api/alerts                  → {scope, pattern, label, terminal_id}
DELETE /api/alerts/{id}
GET    /api/alert-events?since=&terminal_id=
GET    /api/workspaces              → [workspace]
POST   /api/workspaces              → {workspace_id, env, startup_commands}
GET    /api/workspaces/{id}
POST   /api/workspaces/{id}         → {set_env, startup_commands, apply_to_members}
POST   /api/workspaces/{id}/members → {terminal_id}
DELETE /api/workspaces/{id}/members/{tid}
POST   /api/workspaces/{id}/apply   → apply to all members
GET    /api/checkpoints?terminal_id=
POST   /api/checkpoints             → {terminal_id, label, note}
DELETE /api/checkpoints/{id}
GET    /api/export/{id}             → full session snapshot JSON
POST   /api/import                  → {snapshot}
WS     /ws/{id}?since=N             → WebSocket stream
```

**WebSocket message types** (server → client):
- `{type:"history", events:[...], cursor:N}` — replayed history on connect
- `{type:"output", text:"...", cursor:N}` — live PTY output
- `{type:"status", status:{alive, pid, ...}}` — terminal status update

**WebSocket message types** (client → server):
- `{type:"input", text:"..."}` — send raw bytes to PTY
- `{type:"resize", rows:N, cols:N}` — resize PTY

---

## Known issues / tech debt

1. **Python parity gap**: Python `web.py` frontend is the old version — the new warm-stone UI only lives in `rust/index.html`. Should be synced.

2. **DB migration brittleness**: Migrations use `ALTER TABLE ADD COLUMN ... DEFAULT` with silent error suppression (`let _ = ...`). Works for known column additions but any future schema change needs a new migration line added to `migrate()` in `history.rs`.

3. **No auth**: The MCP server and web server have zero authentication. `DANGEROUSLY_OMIT_AUTH=true` is used for the inspector. Fine for local use, not for network exposure.

4. **Stale per-PID DB files**: Previous versions created `sessions-{PID}.db` files in `~/.local/share/i4z-terminal-mcp/`. These can pile up. Safe to delete manually.

5. **Python test coverage**: Only the Rust implementation has Playwright tests. Python has no automated test coverage.

6. **`wait_for_output` timeout behavior**: If a terminal dies while waiting, the tool hangs until timeout rather than failing fast.

---

## Possible next work

- [ ] Add auth (API key via env var) for network deployment
- [ ] Sync Python frontend with new Rust UI (`python/terminal/web.py`)
- [ ] Terminal search highlight: currently regex escaping in frontend is naive (escapes the query before building the highlight regex — needs fixing for real regex searches)
- [ ] Proper schema versioning (`schema_version` table) instead of `ALTER TABLE` accumulation
- [ ] Python Playwright test suite parity
- [ ] `wait_for_output` fast-fail when terminal dies
- [ ] Export/import via UI file picker (currently paste-JSON only)
- [ ] Workspace membership shown on sidebar terminal items
