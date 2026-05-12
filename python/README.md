# i4z-terminal-mcp (Python)

Python reference implementation — asyncio, pexpect PTY, SQLite history, Starlette web server with xterm.js frontend.

```mermaid
graph TB
    subgraph "Callers"
        AI[AI Agent<br/>MCP stdio]
        BROWSER[Browser<br/>HTTP / WebSocket]
    end

    subgraph "Python Process"
        MCP[MCP Server<br/>server.py]
        SM[SessionManager<br/>manager.py]
        HS[HistoryStore<br/>history.py<br/>SQLite]
        WEB[Web Server<br/>web.py<br/>Starlette + xterm.js]
        PTY[PTY Shells<br/>pexpect /bin/bash]
        READER[Reader Loop<br/>reader.py<br/>50ms poll]
    end

    AI -->|JSON-RPC| MCP
    BROWSER -->|REST + WS| WEB
    MCP --> SM
    WEB --> SM
    SM --> HS
    SM --> PTY
    SM --> READER
    READER --> PTY
```

## Structure

```
python/
├── terminal/
│   ├── server.py       # MCP entry point, stdio transport, tool dispatch
│   ├── tools.py        # 34 MCP tool JSON schemas
│   ├── manager.py      # SessionManager: lifecycle, profiles, workspaces, alerts
│   ├── history.py      # HistoryStore: SQLite events/profiles/alerts/bookmarks
│   ├── session.py      # TerminalSession: PTY wrapper, output buffer, cursor
│   ├── reader.py       # Background asyncio reader (50ms poll)
│   ├── signals.py      # POSIX signal dispatch (SIGINT/TERM/KILL)
│   ├── web.py          # Starlette web server + xterm.js HTML UI + REST + WS
│   └── log.py          # Structured stderr logger with prefixes
├── pyproject.toml      # Package metadata, hatchling build, entry point
├── requirements.txt
├── demo.py             # MCP client demo (create, send, read, kill)
└── test.html           # Browser test page
```

## How It Works

### Terminal Lifecycle

```mermaid
sequenceDiagram
    participant Agent as AI Agent
    participant MCP as MCP Server
    participant SM as SessionManager
    participant PTY as PTY Shell
    participant DB as SQLite

    Agent->>MCP: create_terminal(name)
    MCP->>SM: create(name)
    SM->>PTY: pexpect.spawn(/bin/bash)
    SM->>DB: save profile + clear errors
    SM->>PTY: send startup commands
    SM-->>MCP: terminal_id
    MCP-->>Agent: {terminal_id, status: created}

    Agent->>MCP: send_input(id, text)
    MCP->>SM: send(id, text)
    SM->>PTY: send text to stdin
    SM->>DB: record input event
    SM-->>Agent: {status: sent}

    Note over PTY: reader loop polls every 50ms
    PTY-->>SM: output captured
    SM->>DB: record output (ANSI-stripped)
    SM->>SM: check alert patterns

    Agent->>MCP: read_output(id, since)
    MCP->>SM: read(id, since, max_bytes)
    SM-->>Agent: {output, cursor}

    Agent->>MCP: kill_terminal(id)
    MCP->>SM: kill(id)
    SM->>PTY: terminate(force=True)
    SM->>SM: cancel reader task
    SM-->>Agent: {status: killed}
```

### Key Design Decisions

| Decision | Why |
|---|---|
| asyncio event loop | Non-blocking I/O for MCP stdio + web server + 20 PTY readers |
| SQLite per-process (pid in filename) | No cross-contamination between server instances |
| ANSI stripped before DB | Clean history for search; raw output still in memory buffer |
| Output buffer = deque(maxlen=5000) | Bounded memory, cursor-based incremental reads |
| Reader loop polls every 50ms | Tradeoff: simpler than select-based, low enough latency |
| Workspace = env + startup + member list | Group terminals with shared configuration |
| Alerts = pattern-on-output watchers | Global or per-session, fire alert events |
| Checkpoints = named cursor positions | Reference points in output history for later lookup |

### Running

```bash
cd python && pip install -e .
i4z-terminal-mcp                           # random web port
I4Z_TERMINAL_WEB_PORT=9020 i4z-terminal-mcp  # fixed port
```

### Configuration

| Env Var | Default | Description |
|---|---|---|
| `I4Z_TERMINAL_WEB_PORT` | random free | Web UI listen port |
| `I4Z_TERMINAL_WEB_HOST` | `0.0.0.0` | Web UI bind address |
| `I4Z_TERMINAL_STATE_DIR` | `~/.local/share/i4z-terminal-mcp` | SQLite storage |
