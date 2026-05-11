import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone

from .log import log

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]|\x1b\][^\x07]*\x07")


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).replace("\r", "")


def _db_path() -> str:
    state_dir = os.environ.get("I4Z_TERMINAL_STATE_DIR", "")
    if not state_dir:
        state_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "i4z-terminal-mcp")
    os.makedirs(state_dir, exist_ok=True)
    return os.path.join(state_dir, f"sessions-{os.getpid()}.db")


class HistoryStore:
    def __init__(self):
        self.db_path = _db_path()
        log(f"SQLite: {self.db_path}", "DB")
        self._db: sqlite3.Connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  terminal_id TEXT NOT NULL,"
            "  type TEXT NOT NULL CHECK(type IN ('input','output')),"
            "  text TEXT NOT NULL,"
            "  timestamp TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_terminal ON events(terminal_id, id)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS session_profiles ("
            "  terminal_id TEXT PRIMARY KEY,"
            "  env_json TEXT NOT NULL,"
            "  startup_json TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS alerts ("
            "  id TEXT PRIMARY KEY,"
            "  scope TEXT NOT NULL CHECK(scope IN ('global','session')),"
            "  terminal_id TEXT,"
            "  pattern TEXT NOT NULL,"
            "  label TEXT,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_scope ON alerts(scope, terminal_id)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS alert_events ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  alert_id TEXT NOT NULL,"
            "  terminal_id TEXT NOT NULL,"
            "  pattern TEXT NOT NULL,"
            "  matched_text TEXT NOT NULL,"
            "  timestamp TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_alert_events_terminal ON alert_events(terminal_id, id)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS reader_errors ("
            "  terminal_id TEXT PRIMARY KEY,"
            "  message TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS bookmarks ("
            "  id TEXT PRIMARY KEY,"
            "  terminal_id TEXT NOT NULL,"
            "  cursor INTEGER NOT NULL,"
            "  label TEXT NOT NULL,"
            "  note TEXT,"
            "  created_at TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_bookmarks_terminal ON bookmarks(terminal_id, created_at)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS workspaces ("
            "  id TEXT PRIMARY KEY,"
            "  env_json TEXT NOT NULL,"
            "  startup_json TEXT NOT NULL,"
            "  created_at TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS workspace_members ("
            "  workspace_id TEXT NOT NULL,"
            "  terminal_id TEXT NOT NULL,"
            "  created_at TEXT NOT NULL,"
            "  PRIMARY KEY (workspace_id, terminal_id)"
            ")"
        )
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_workspace_members_terminal ON workspace_members(terminal_id)"
        )

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _fetch_profile_row(self, terminal_id: str):
        return self._db.execute(
            "SELECT env_json, startup_json FROM session_profiles WHERE terminal_id = ?",
            (terminal_id,),
        ).fetchone()

    def record(self, terminal_id: str, event_type: str, text: str) -> None:
        if event_type == "output":
            text = _strip_ansi(text)
        if not text:
            return
        self._db.execute(
            "INSERT INTO events (terminal_id, type, text, timestamp) VALUES (?, ?, ?, ?)",
            (terminal_id, event_type, text, self._now()),
        )
        self._db.commit()

    def make_output_callback(self, terminal_id: str):
        def cb(text: str) -> None:
            self.record(terminal_id, "output", text)

        return cb

    def get_history(self, terminal_id: str, since: int = 0) -> dict:
        rows = self._db.execute(
            "SELECT id, type, text, timestamp FROM events "
            "WHERE terminal_id = ? AND id > ? ORDER BY id",
            (terminal_id, since),
        ).fetchall()
        if not rows:
            has_any_events = self._db.execute(
                "SELECT 1 FROM events WHERE terminal_id = ? LIMIT 1",
                (terminal_id,),
            ).fetchone()
            if not has_any_events:
                raise KeyError(f"Terminal '{terminal_id}' not found")

        events = [
            {"id": row["id"], "type": row["type"], "text": row["text"], "timestamp": row["timestamp"]}
            for row in rows
        ]
        latest = events[-1]["id"] if events else since
        return {"events": events, "cursor": latest}

    def list_terminal_ids(self) -> list[str]:
        rows = self._db.execute(
            "SELECT terminal_id FROM ("
            "  SELECT DISTINCT terminal_id FROM events"
            "  UNION"
            "  SELECT terminal_id FROM session_profiles"
            "  UNION"
            "  SELECT terminal_id FROM alerts WHERE terminal_id IS NOT NULL"
            "  UNION"
            "  SELECT terminal_id FROM reader_errors"
            ") ORDER BY terminal_id"
        ).fetchall()
        return [row["terminal_id"] for row in rows]

    def status(self, terminal_id: str) -> dict:
        row = self._db.execute(
            "SELECT timestamp FROM events WHERE terminal_id = ? ORDER BY id ASC LIMIT 1",
            (terminal_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Terminal '{terminal_id}' not found")

        last_row = self._db.execute(
            "SELECT timestamp FROM events WHERE terminal_id = ? ORDER BY id DESC LIMIT 1",
            (terminal_id,),
        ).fetchone()
        return {
            "id": terminal_id,
            "alive": False,
            "pid": None,
            "cwd": None,
            "created_at": row["timestamp"],
            "last_activity": last_row["timestamp"] if last_row else row["timestamp"],
            "reader_error": self.get_reader_error(terminal_id),
        }

    def search(self, terminal_id: str, query: str) -> dict:
        has_any_events = self._db.execute(
            "SELECT 1 FROM events WHERE terminal_id = ? LIMIT 1",
            (terminal_id,),
        ).fetchone()
        if not has_any_events:
            raise KeyError(f"Terminal '{terminal_id}' not found")
        rows = self._db.execute(
            "SELECT text FROM events WHERE terminal_id = ? AND LOWER(text) LIKE ? ORDER BY id",
            (terminal_id, f"%{query.lower()}%"),
        ).fetchall()
        return {"matches": [row["text"].strip() for row in rows if row["text"].strip()]}

    def get_session_profile(self, terminal_id: str) -> dict:
        row = self._fetch_profile_row(terminal_id)
        if not row:
            return {"env": {}, "startup_commands": []}
        return {
            "env": json.loads(row["env_json"]),
            "startup_commands": json.loads(row["startup_json"]),
        }

    def set_session_env(self, terminal_id: str, key: str, value: str) -> dict:
        profile = self.get_session_profile(terminal_id)
        env = dict(profile["env"])
        env[key] = value
        self._save_session_profile(terminal_id, env, profile["startup_commands"])
        return self.get_session_profile(terminal_id)

    def unset_session_env(self, terminal_id: str, key: str) -> dict:
        profile = self.get_session_profile(terminal_id)
        env = dict(profile["env"])
        env.pop(key, None)
        self._save_session_profile(terminal_id, env, profile["startup_commands"])
        return self.get_session_profile(terminal_id)

    def set_session_startup_commands(self, terminal_id: str, commands: list[str]) -> dict:
        profile = self.get_session_profile(terminal_id)
        self._save_session_profile(terminal_id, profile["env"], commands)
        return self.get_session_profile(terminal_id)

    def save_session_profile(self, terminal_id: str, env: dict[str, str], startup_commands: list[str]) -> dict:
        self._save_session_profile(terminal_id, env, startup_commands)
        return self.get_session_profile(terminal_id)

    def _save_session_profile(self, terminal_id: str, env: dict[str, str], startup_commands: list[str]) -> None:
        self._db.execute(
            "INSERT INTO session_profiles (terminal_id, env_json, startup_json, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(terminal_id) DO UPDATE SET env_json=excluded.env_json, startup_json=excluded.startup_json, updated_at=excluded.updated_at",
            (terminal_id, json.dumps(env, sort_keys=True), json.dumps(startup_commands), self._now()),
        )
        self._db.commit()

    def add_alert(self, scope: str, pattern: str, terminal_id: str | None = None, label: str | None = None) -> dict:
        if scope not in {"global", "session"}:
            raise ValueError("scope must be 'global' or 'session'")
        if scope == "session" and not terminal_id:
            raise ValueError("terminal_id is required for session alerts")
        alert_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO alerts (id, scope, terminal_id, pattern, label, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (alert_id, scope, terminal_id, pattern, label, self._now()),
        )
        self._db.commit()
        return {
            "id": alert_id,
            "scope": scope,
            "terminal_id": terminal_id,
            "pattern": pattern,
            "label": label,
        }

    def list_alerts(self, scope: str | None = None, terminal_id: str | None = None) -> list[dict]:
        query = "SELECT id, scope, terminal_id, pattern, label, created_at FROM alerts"
        clauses: list[str] = []
        params: list[str] = []
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if terminal_id:
            clauses.append("(terminal_id = ? OR terminal_id IS NULL)")
            params.append(terminal_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at, id"
        rows = self._db.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "scope": row["scope"],
                "terminal_id": row["terminal_id"],
                "pattern": row["pattern"],
                "label": row["label"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def remove_alert(self, alert_id: str) -> bool:
        cur = self._db.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        self._db.commit()
        return cur.rowcount > 0

    def observe_output(self, terminal_id: str, text: str) -> list[dict]:
        if not text:
            return []
        clean_text = _strip_ansi(text)
        rows = self._db.execute(
            "SELECT id, scope, terminal_id, pattern, label FROM alerts "
            "WHERE scope = 'global' OR terminal_id = ?",
            (terminal_id,),
        ).fetchall()
        hits: list[dict] = []
        for row in rows:
            pattern = row["pattern"]
            if pattern and pattern.lower() in clean_text.lower():
                hit = {
                    "alert_id": row["id"],
                    "terminal_id": terminal_id,
                    "pattern": pattern,
                    "label": row["label"],
                    "matched_text": clean_text.strip(),
                    "timestamp": self._now(),
                }
                self._db.execute(
                    "INSERT INTO alert_events (alert_id, terminal_id, pattern, matched_text, timestamp) VALUES (?, ?, ?, ?, ?)",
                    (hit["alert_id"], terminal_id, pattern, hit["matched_text"], hit["timestamp"]),
                )
                hits.append(hit)
        if hits:
            self._db.commit()
        return hits

    def list_alert_events(self, terminal_id: str | None = None, since: int = 0) -> list[dict]:
        query = "SELECT id, alert_id, terminal_id, pattern, matched_text, timestamp FROM alert_events WHERE id > ?"
        params: list[object] = [since]
        if terminal_id:
            query += " AND terminal_id = ?"
            params.append(terminal_id)
        query += " ORDER BY id"
        rows = self._db.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "alert_id": row["alert_id"],
                "terminal_id": row["terminal_id"],
                "pattern": row["pattern"],
                "matched_text": row["matched_text"],
                "timestamp": row["timestamp"],
            }
            for row in rows
        ]

    def record_reader_error(self, terminal_id: str, message: str) -> None:
        self._db.execute(
            "INSERT INTO reader_errors (terminal_id, message, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(terminal_id) DO UPDATE SET message=excluded.message, updated_at=excluded.updated_at",
            (terminal_id, message, self._now()),
        )
        self._db.commit()

    def clear_reader_error(self, terminal_id: str) -> None:
        self._db.execute("DELETE FROM reader_errors WHERE terminal_id = ?", (terminal_id,))
        self._db.commit()

    def get_reader_error(self, terminal_id: str) -> str | None:
        row = self._db.execute(
            "SELECT message FROM reader_errors WHERE terminal_id = ?",
            (terminal_id,),
        ).fetchone()
        return row["message"] if row else None

    def list_reader_errors(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT terminal_id, message, updated_at FROM reader_errors ORDER BY updated_at DESC"
        ).fetchall()
        return [
            {
                "terminal_id": row["terminal_id"],
                "message": row["message"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def health(self, active_sessions: dict, stale_after_seconds: int = 300) -> dict:
        now = datetime.now(timezone.utc)
        active = []
        stale = []
        for session in active_sessions.values():
            item = {
                "id": session.id,
                "alive": session.alive,
                "pid": session.get_pid(),
                "last_activity": session.updated_at.isoformat(),
            }
            active.append(item)
            age = (now - session.updated_at).total_seconds()
            if session.alive and age >= stale_after_seconds:
                stale.append(item)

        counts = {
            "events": self._db.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"],
            "profiles": self._db.execute("SELECT COUNT(*) AS c FROM session_profiles").fetchone()["c"],
            "alerts": self._db.execute("SELECT COUNT(*) AS c FROM alerts").fetchone()["c"],
            "alert_events": self._db.execute("SELECT COUNT(*) AS c FROM alert_events").fetchone()["c"],
            "reader_errors": self._db.execute("SELECT COUNT(*) AS c FROM reader_errors").fetchone()["c"],
            "bookmarks": self._db.execute("SELECT COUNT(*) AS c FROM bookmarks").fetchone()["c"],
            "workspaces": self._db.execute("SELECT COUNT(*) AS c FROM workspaces").fetchone()["c"],
            "workspace_members": self._db.execute("SELECT COUNT(*) AS c FROM workspace_members").fetchone()["c"],
        }
        return {
            "db": {"path": self.db_path, "ok": True},
            "counts": counts,
            "sessions": {
                "active": len(active),
                "stale": stale,
                "known": self.list_terminal_ids(),
            },
            "reader_errors": self.list_reader_errors(),
            "alerts": self.list_alerts(),
            "bookmarks": self.list_bookmarks(),
            "workspaces": self.list_workspaces(),
        }

    def add_bookmark(self, terminal_id: str, cursor: int, label: str, note: str | None = None) -> dict:
        bookmark_id = uuid.uuid4().hex
        self._db.execute(
            "INSERT INTO bookmarks (id, terminal_id, cursor, label, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (bookmark_id, terminal_id, cursor, label, note, self._now()),
        )
        self._db.commit()
        return {
            "id": bookmark_id,
            "terminal_id": terminal_id,
            "cursor": cursor,
            "label": label,
            "note": note,
        }

    def list_bookmarks(self, terminal_id: str | None = None) -> list[dict]:
        query = "SELECT id, terminal_id, cursor, label, note, created_at FROM bookmarks"
        params: list[object] = []
        if terminal_id:
            query += " WHERE terminal_id = ?"
            params.append(terminal_id)
        query += " ORDER BY created_at, id"
        rows = self._db.execute(query, params).fetchall()
        return [
            {
                "id": row["id"],
                "terminal_id": row["terminal_id"],
                "cursor": row["cursor"],
                "label": row["label"],
                "note": row["note"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def remove_bookmark(self, bookmark_id: str) -> bool:
        cur = self._db.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
        self._db.commit()
        return cur.rowcount > 0

    def create_workspace(self, workspace_id: str, env: dict[str, str] | None = None, startup_commands: list[str] | None = None) -> dict:
        if self._db.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone():
            raise ValueError(f"Workspace '{workspace_id}' already exists")
        env_json = json.dumps(env or {}, sort_keys=True)
        startup_json = json.dumps(startup_commands or [])
        now = self._now()
        self._db.execute(
            "INSERT INTO workspaces (id, env_json, startup_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (workspace_id, env_json, startup_json, now, now),
        )
        self._db.commit()
        return self.get_workspace(workspace_id)

    def get_workspace(self, workspace_id: str) -> dict:
        row = self._db.execute(
            "SELECT id, env_json, startup_json, created_at, updated_at FROM workspaces WHERE id = ?",
            (workspace_id,),
        ).fetchone()
        if not row:
            raise KeyError(f"Workspace '{workspace_id}' not found")
        return {
            "id": row["id"],
            "env": json.loads(row["env_json"]),
            "startup_commands": json.loads(row["startup_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "members": self.list_workspace_members(workspace_id),
        }

    def list_workspaces(self) -> list[dict]:
        rows = self._db.execute(
            "SELECT w.id, w.env_json, w.startup_json, w.created_at, w.updated_at, COUNT(m.terminal_id) AS member_count "
            "FROM workspaces w "
            "LEFT JOIN workspace_members m ON m.workspace_id = w.id "
            "GROUP BY w.id, w.env_json, w.startup_json, w.created_at, w.updated_at "
            "ORDER BY w.id"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "env": json.loads(row["env_json"]),
                "startup_commands": json.loads(row["startup_json"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "member_count": row["member_count"],
            }
            for row in rows
        ]

    def update_workspace(self, workspace_id: str, env: dict[str, str], startup_commands: list[str]) -> dict:
        now = self._now()
        cur = self._db.execute(
            "UPDATE workspaces SET env_json = ?, startup_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(env, sort_keys=True), json.dumps(startup_commands), now, workspace_id),
        )
        if cur.rowcount == 0:
            raise KeyError(f"Workspace '{workspace_id}' not found")
        self._db.commit()
        return self.get_workspace(workspace_id)

    def add_workspace_member(self, workspace_id: str, terminal_id: str) -> None:
        if not self._db.execute("SELECT 1 FROM workspaces WHERE id = ?", (workspace_id,)).fetchone():
            raise KeyError(f"Workspace '{workspace_id}' not found")
        self._db.execute(
            "INSERT OR IGNORE INTO workspace_members (workspace_id, terminal_id, created_at) VALUES (?, ?, ?)",
            (workspace_id, terminal_id, self._now()),
        )
        self._db.commit()

    def remove_workspace_member(self, workspace_id: str, terminal_id: str) -> None:
        self._db.execute(
            "DELETE FROM workspace_members WHERE workspace_id = ? AND terminal_id = ?",
            (workspace_id, terminal_id),
        )
        self._db.commit()

    def list_workspace_members(self, workspace_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT terminal_id FROM workspace_members WHERE workspace_id = ? ORDER BY terminal_id",
            (workspace_id,),
        ).fetchall()
        return [row["terminal_id"] for row in rows]

    def list_workspace_ids_for_terminal(self, terminal_id: str) -> list[str]:
        rows = self._db.execute(
            "SELECT workspace_id FROM workspace_members WHERE terminal_id = ? ORDER BY workspace_id",
            (terminal_id,),
        ).fetchall()
        return [row["workspace_id"] for row in rows]

    def remove_workspace(self, workspace_id: str) -> bool:
        self._db.execute("DELETE FROM workspace_members WHERE workspace_id = ?", (workspace_id,))
        cur = self._db.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        self._db.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._db.close()
