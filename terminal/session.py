import asyncio
import os
from collections import deque
from collections.abc import Callable
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
    on_output: Callable[[str], None] | None = None
    on_error: Callable[[str], None] | None = None
    output_listeners: list[Callable[[str], None]] = field(default_factory=list)

    def append_output(self, text: str) -> None:
        if not text:
            return
        entry = (self.cursor, text)
        self.output_buffer.append(entry)
        self.cursor += len(text)
        self.updated_at = datetime.now(timezone.utc)
        if self.on_output:
            self.on_output(text)
        for listener in list(self.output_listeners):
            listener(text)

    def add_output_listener(self, listener: Callable[[str], None]) -> None:
        if listener not in self.output_listeners:
            self.output_listeners.append(listener)

    def remove_output_listener(self, listener: Callable[[str], None]) -> None:
        try:
            self.output_listeners.remove(listener)
        except ValueError:
            pass

    def read_since(self, since: int, max_bytes: int | None = None) -> tuple[str, int]:
        chunks: list[str] = []
        total = 0
        next_cursor = since
        for offset, text in self.output_buffer:
            if offset + len(text) <= since:
                continue
            start = max(0, since - offset)
            chunk = text[start:]
            if max_bytes is not None and total + len(chunk) > max_bytes:
                remaining = max_bytes - total
                if remaining > 0:
                    piece = chunk[:remaining]
                    chunks.append(piece)
                    next_cursor = offset + start + len(piece)
                break
            chunks.append(chunk)
            total += len(chunk)
            next_cursor = offset + start + len(chunk)
        output = "".join(chunks)
        return output, next_cursor

    def search_output(self, query: str) -> list[str]:
        matches: list[str] = []
        for _, text in self.output_buffer:
            for line in text.split("\n"):
                if query.lower() in line.lower():
                    matches.append(line.strip())
        return matches

    def output_text(self) -> str:
        return "".join(text for _, text in self.output_buffer)

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

    def resize(self, rows: int, cols: int) -> None:
        try:
            self.shell.setwinsize(rows, cols)
        except Exception:
            pass
