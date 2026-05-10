import asyncio
import time
from datetime import datetime, timezone

import pexpect

from .session import TerminalSession
from .reader import reader_loop
from .signals import send_signal


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}

    async def create(self, name: str) -> TerminalSession:
        if name in self._sessions:
            raise ValueError(f"Terminal '{name}' already exists")

        shell = pexpect.spawn("/bin/bash", encoding="utf-8", codec_errors="replace")
        shell.setwinsize(24, 80)

        session = TerminalSession(id=name, shell=shell)

        task = asyncio.create_task(reader_loop(session))
        session.reader_task = task

        self._sessions[name] = session
        return session

    def get(self, name: str) -> TerminalSession:
        if name not in self._sessions:
            raise KeyError(f"Terminal '{name}' not found")
        return self._sessions[name]

    def list_all(self) -> list[dict]:
        return [
            {"id": s.id, "alive": s.alive}
            for s in self._sessions.values()
        ]

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
        session.shell.send(text)
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
