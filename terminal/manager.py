import asyncio
import os
import re
import sqlite3
import time
from datetime import datetime, timezone

import pexpect

from .session import TerminalSession
from .reader import reader_loop
from .signals import send_signal
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


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}
        self.web_url: str | None = None
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

    def _record(self, terminal_id: str, event_type: str, text: str) -> None:
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

    def _make_output_callback(self, terminal_id: str):
        def cb(text: str) -> None:
            self._record(terminal_id, "output", text)
        return cb

    def get_history(self, name: str, since: int = 0) -> dict:
        # Allow querying history even for dead terminals (they have events in DB)
        # Only check if the terminal has ANY events in the database
        rows = self._db.execute(
            "SELECT id, type, text, timestamp FROM events "
            "WHERE terminal_id = ? AND id > ? ORDER BY id",
            (name, since),
        ).fetchall()
        
        # If no events found, check if the terminal ever existed
        if not rows:
            has_any_events = self._db.execute(
                "SELECT 1 FROM events WHERE terminal_id = ? LIMIT 1",
                (name,),
            ).fetchone()
            if not has_any_events and name not in self._sessions:
                raise KeyError(f"Terminal '{name}' not found")
        
        events = [
            {"id": r[0], "type": r[1], "text": r[2], "timestamp": r[3]}
            for r in rows
        ]
        latest = events[-1]["id"] if events else since
        return {"events": events, "cursor": latest}

    async def create(self, name: str) -> TerminalSession:
        if name in self._sessions:
            raise ValueError(f"Terminal '{name}' already exists")

        env = os.environ.copy()
        env.update(
            {
                "TERM": "dumb",
                "NO_COLOR": "1",
                "CLICOLOR": "0",
                "LS_COLORS": "",
                "PS1": "$ ",
                "PROMPT_COMMAND": "",
            }
        )
        shell = pexpect.spawn(
            "/bin/bash",
            ["--noprofile", "--norc"],
            encoding="utf-8",
            codec_errors="replace",
            env=env,
        )
        shell.setwinsize(24, 80)

        session = TerminalSession(id=name, shell=shell)
        session.on_output = self._make_output_callback(name)

        task = asyncio.create_task(reader_loop(session))
        session.reader_task = task

        self._sessions[name] = session
        return session

    def get(self, name: str) -> TerminalSession:
        if name not in self._sessions:
            raise KeyError(f"Terminal '{name}' not found")
        return self._sessions[name]

    def list_all(self) -> list[dict]:
        # Get all currently active sessions
        active = {
            s.id: {"id": s.id, "alive": s.alive}
            for s in self._sessions.values()
        }
        
        # Add sessions with history but no longer active
        dead_sessions = self._db.execute(
            "SELECT DISTINCT terminal_id FROM events"
        ).fetchall()
        
        for (term_id,) in dead_sessions:
            if term_id not in active:
                active[term_id] = {"id": term_id, "alive": False}
        
        return list(active.values())

    def status(self, name: str) -> dict:
        session = self.get(name)
        cwd = session.get_cwd()
        return {
            "id": session.id,
            "alive": session.alive,
            "pid": session.get_pid(),
            "cwd": cwd,
            "created_at": session.created_at.isoformat(),
            "last_activity": session.updated_at.isoformat(),
        }

    def send(self, name: str, text: str) -> None:
        session = self.get(name)
        if not session.alive:
            raise RuntimeError(f"Terminal '{name}' is dead")
        send_text = text if text.endswith(("\n", "\r")) else text + "\n"
        session.shell.send(send_text)
        self._record(name, "input", text)
        session.updated_at = datetime.now(timezone.utc)

    def read(self, name: str, since: int = 0, max_bytes: int | None = None) -> dict:
        session = self.get(name)
        output, cursor = session.read_since(since, max_bytes)
        return {"output": output, "cursor": cursor}

    def signal(self, name: str, sig: str) -> None:
        session = self.get(name)
        if not send_signal(session, sig):
            raise ValueError(f"Unsupported signal: {sig}")

    async def wait_for(self, name: str, pattern: str, timeout: float = 30) -> dict:
        session = self.get(name)
        start = time.time()
        while time.time() - start < timeout:
            output = "".join(text for _, text in session.output_buffer)
            if pattern in output:
                return {"matched": True, "cursor": session.cursor}
            await asyncio.sleep(0.1)
        return {"matched": False, "cursor": session.cursor}

    def search(self, name: str, query: str) -> dict:
        session = self.get(name)
        matches = session.search_output(query)
        return {"matches": matches}

    async def kill(self, name: str) -> None:
        session = self.get(name)
        session.alive = False
        try:
            session.shell.terminate(force=True)
        except Exception:
            pass
        if session.reader_task:
            session.reader_task.cancel()
            try:
                await session.reader_task
            except asyncio.CancelledError:
                pass
        self._sessions.pop(name, None)

    async def shutdown(self) -> None:
        for name in list(self._sessions.keys()):
            await self.kill(name)
        self._db.close()
