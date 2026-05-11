import os
import re
import sqlite3
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
        path = _db_path()
        log(f"SQLite: {path}", "DB")
        self._db: sqlite3.Connection = sqlite3.connect(path, check_same_thread=False)
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

    def record(self, terminal_id: str, event_type: str, text: str) -> None:
        if event_type == "output":
            text = _strip_ansi(text)
        if not text:
            return
        ts = datetime.now(timezone.utc).isoformat()
        self._db.execute(
            "INSERT INTO events (terminal_id, type, text, timestamp) VALUES (?, ?, ?, ?)",
            (terminal_id, event_type, text, ts),
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
            {"id": row[0], "type": row[1], "text": row[2], "timestamp": row[3]}
            for row in rows
        ]
        latest = events[-1]["id"] if events else since
        return {"events": events, "cursor": latest}

    def list_terminal_ids(self) -> list[str]:
        rows = self._db.execute("SELECT DISTINCT terminal_id FROM events ORDER BY terminal_id").fetchall()
        return [row[0] for row in rows]

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
            "created_at": row[0],
            "last_activity": last_row[0] if last_row else row[0],
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
        return {"matches": [row[0].strip() for row in rows if row[0].strip()]}

    def close(self) -> None:
        self._db.close()
