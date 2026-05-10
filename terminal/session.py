import asyncio
import os
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

MAX_BUFFER = 5000


@dataclass
class TerminalSession:
    id: str
    shell: object  # pexpect.spawn
    output_buffer: deque = field(default_factory=lambda: deque(maxlen=MAX_BUFFER))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    cursor: int = 0
    alive: bool = True
    reader_task: asyncio.Task | None = None

    def append_output(self, text: str) -> None:
        if not text:
            return
        entry = (self.cursor, text)
        self.output_buffer.append(entry)
        self.cursor += len(text)
        self.updated_at = datetime.now(timezone.utc)

    def read_since(self, since: int, max_bytes: int | None = None) -> tuple[str, int]:
        chunks: list[str] = []
        total = 0
        for offset, text in self.output_buffer:
            if offset + len(text) <= since:
                continue
            start = max(0, since - offset)
            chunk = text[start:]
            if max_bytes is not None and total + len(chunk) > max_bytes:
                remaining = max_bytes - total
                if remaining > 0:
                    chunks.append(chunk[:remaining])
                break
            chunks.append(chunk)
            total += len(chunk)
        output = "".join(chunks)
        return output, self.cursor

    def search_output(self, query: str) -> list[str]:
        matches: list[str] = []
        for _, text in self.output_buffer:
            for line in text.split("\n"):
                if query.lower() in line.lower():
                    matches.append(line.strip())
        return matches

    def get_pid(self) -> int | None:
        try:
            return self.shell.pid
        except Exception:
            return None

    def get_cwd(self) -> str | None:
        try:
            return os.readlink(f"/proc/{self.shell.pid}/cwd")
        except Exception:
            return None
