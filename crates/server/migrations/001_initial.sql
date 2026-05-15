CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id TEXT    NOT NULL,
    kind        TEXT    NOT NULL, -- 'input' | 'output'
    data        TEXT    NOT NULL,
    ts          INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_events_terminal ON events(terminal_id);

CREATE TABLE IF NOT EXISTS session_profiles (
    terminal_id          TEXT PRIMARY KEY,
    env_json             TEXT NOT NULL DEFAULT '{}',
    startup_cmds_json    TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope       TEXT    NOT NULL, -- 'global' | 'session'
    terminal_id TEXT,
    pattern     TEXT    NOT NULL,
    label       TEXT
);

CREATE TABLE IF NOT EXISTS alert_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    INTEGER NOT NULL,
    terminal_id TEXT    NOT NULL,
    matched     TEXT,
    ts          INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_aev_terminal ON alert_events(terminal_id);

CREATE TABLE IF NOT EXISTS workspaces (
    id                TEXT PRIMARY KEY,
    env_json          TEXT NOT NULL DEFAULT '{}',
    startup_cmds_json TEXT NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS workspace_members (
    workspace_id TEXT NOT NULL,
    terminal_id  TEXT NOT NULL,
    PRIMARY KEY (workspace_id, terminal_id)
);

CREATE TABLE IF NOT EXISTS checkpoints (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id TEXT    NOT NULL,
    label       TEXT    NOT NULL,
    note        TEXT,
    cursor      INTEGER,
    ts          INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_cp_terminal ON checkpoints(terminal_id);

CREATE TABLE IF NOT EXISTS reader_errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    terminal_id TEXT    NOT NULL,
    message     TEXT    NOT NULL,
    ts          INTEGER NOT NULL DEFAULT (unixepoch())
);
