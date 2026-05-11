import asyncio
import os
import re
import shlex
import time
from datetime import datetime, timezone

import pexpect

from .history import HistoryStore
from .log import log
from .reader import reader_loop
from .session import TerminalSession
from .signals import send_signal

_ROUTE_SAFE_ID_RE = re.compile(r"^[^\x00-\x1f\x7f/\\]+$")
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _validate_route_id(value: str, label: str) -> None:
    if not value:
        raise ValueError(f"{label} cannot be empty")
    if not _ROUTE_SAFE_ID_RE.fullmatch(value):
        raise ValueError(f"{label} cannot contain path separators or control characters")


def _validate_env_key(key: str) -> None:
    if not _ENV_KEY_RE.fullmatch(key):
        raise ValueError(f"Invalid environment variable name: {key!r}")


class SessionManager:
    def __init__(self):
        self._sessions: dict[str, TerminalSession] = {}
        self._history = HistoryStore()
        self.web_url: str | None = None

    def get_history(self, name: str, since: int = 0) -> dict:
        return self._history.get_history(name, since)

    def get_profile(self, name: str) -> dict:
        return self._history.get_session_profile(name)

    def get_workspace(self, workspace_id: str) -> dict:
        return self._history.get_workspace(workspace_id)

    def list_workspaces(self) -> list[dict]:
        return self._history.list_workspaces()

    def workspace_status(self, workspace_id: str) -> dict:
        return self._history.get_workspace(workspace_id)

    def create_workspace(
        self,
        workspace_id: str,
        env: dict[str, str] | None = None,
        startup_commands: list[str] | None = None,
    ) -> dict:
        _validate_route_id(workspace_id, "Workspace id")
        return self._history.create_workspace(workspace_id, env, startup_commands)

    def configure_workspace(
        self,
        workspace_id: str,
        set_env: dict[str, str] | None = None,
        unset_env: list[str] | None = None,
        startup_commands: list[str] | None = None,
        apply_to_members: bool = True,
    ) -> dict:
        _validate_route_id(workspace_id, "Workspace id")
        workspace = self._history.get_workspace(workspace_id)
        env = dict(workspace["env"])
        if set_env:
            for key in set_env:
                _validate_env_key(key)
            env.update(set_env)
        if unset_env:
            for key in unset_env:
                _validate_env_key(key)
                env.pop(key, None)
        commands = list(workspace["startup_commands"])
        if startup_commands is not None:
            commands = list(startup_commands)
        workspace = self._history.update_workspace(workspace_id, env, commands)
        applied: list[str] = []
        if apply_to_members:
            for member_id in workspace["members"]:
                session = self._sessions.get(member_id)
                if session:
                    self._apply_workspace_to_session(session, workspace)
                    applied.append(member_id)
        workspace["applied_to"] = applied
        return workspace

    def remove_workspace(self, workspace_id: str) -> bool:
        return self._history.remove_workspace(workspace_id)

    def add_terminal_to_workspace(self, workspace_id: str, terminal_id: str) -> dict:
        self._history.add_workspace_member(workspace_id, terminal_id)
        session = self._sessions.get(terminal_id)
        if session:
            self._apply_workspace_to_session(session, self._history.get_workspace(workspace_id))
        return self._history.get_workspace(workspace_id)

    def remove_terminal_from_workspace(self, workspace_id: str, terminal_id: str) -> dict:
        self._history.remove_workspace_member(workspace_id, terminal_id)
        return self._history.get_workspace(workspace_id)

    def apply_workspace(self, workspace_id: str, terminal_id: str | None = None) -> dict:
        workspace = self._history.get_workspace(workspace_id)
        targets = [terminal_id] if terminal_id else list(workspace["members"])
        applied = []
        for name in targets:
            session = self._sessions.get(name)
            if session:
                self._apply_workspace_to_session(session, workspace)
                applied.append(name)
        return {"workspace_id": workspace_id, "applied_to": applied, "workspace": workspace}

    async def create(
        self,
        name: str,
        env: dict[str, str] | None = None,
        startup_commands: list[str] | None = None,
        workspace_id: str | None = None,
        run_startup_commands: bool = True,
    ) -> TerminalSession:
        name = name.strip()
        _validate_route_id(name, "Terminal name")
        if name in self._sessions:
            raise ValueError(f"Terminal '{name}' already exists")
        if workspace_id:
            _validate_route_id(workspace_id, "Workspace id")

        profile = self._history.get_session_profile(name)
        workspace_profile = {"env": {}, "startup_commands": []}
        if workspace_id:
            workspace_profile = self._history.get_workspace(workspace_id)
        profile_env = dict(profile["env"])
        profile_env.update(workspace_profile["env"])
        if env:
            profile_env.update(env)
        profile_startup = list(profile["startup_commands"])
        profile_startup.extend(workspace_profile["startup_commands"])
        if startup_commands:
            profile_startup.extend(startup_commands)
        self._history.save_session_profile(name, profile_env, profile_startup)
        self._history.clear_reader_error(name)

        spawn_env = os.environ.copy()
        spawn_env.update(
            {
                "TERM": "dumb",
                "NO_COLOR": "1",
                "CLICOLOR": "0",
                "LS_COLORS": "",
                "PS1": "$ ",
                "PROMPT_COMMAND": "",
            }
        )
        spawn_env.update(profile_env)
        shell = pexpect.spawn(
            "/bin/bash",
            ["--noprofile", "--norc"],
            encoding="utf-8",
            codec_errors="replace",
            env=spawn_env,
        )
        shell.setwinsize(24, 80)

        session = TerminalSession(id=name, shell=shell)
        session.on_output = self._make_output_callback(name)
        session.on_error = lambda message: self._history.record_reader_error(name, message)

        task = asyncio.create_task(reader_loop(session))
        session.reader_task = task

        self._sessions[name] = session
        if workspace_id:
            self._history.add_workspace_member(workspace_id, name)
        if profile_startup and run_startup_commands:
            self.run_startup_commands(name, profile_startup)
        return session

    def _make_output_callback(self, terminal_id: str):
        def cb(text: str) -> None:
            self._history.record(terminal_id, "output", text)
            hits = self._history.observe_output(terminal_id, text)
            for hit in hits:
                label = f" [{hit['label']}]" if hit.get("label") else ""
                log(f"ALERT{label} {terminal_id}: pattern={hit['pattern']!r}", "ALERT")

        return cb

    def get(self, name: str) -> TerminalSession:
        if name not in self._sessions:
            raise KeyError(f"Terminal '{name}' not found")
        return self._sessions[name]

    def list_all(self) -> list[dict]:
        active = {s.id: {"id": s.id, "alive": s.alive} for s in self._sessions.values()}
        for term_id in self._history.list_terminal_ids():
            if term_id not in active:
                active[term_id] = {"id": term_id, "alive": False}
        return list(active.values())

    def status(self, name: str) -> dict:
        session = self._sessions.get(name)
        if session:
            return {
                "id": session.id,
                "alive": session.alive,
                "pid": session.get_pid(),
                "cwd": session.get_cwd(),
                "created_at": session.created_at.isoformat(),
                "last_activity": session.updated_at.isoformat(),
                "reader_error": self._history.get_reader_error(name),
                "profile": self.get_profile(name),
                "workspaces": self._history.list_workspace_ids_for_terminal(name),
            }

        data = self._history.status(name)
        data["profile"] = self.get_profile(name)
        data["workspaces"] = self._history.list_workspace_ids_for_terminal(name)
        return data

    def send(self, name: str, text: str) -> None:
        session = self.get(name)
        if not session.alive:
            raise RuntimeError(f"Terminal '{name}' is dead")
        send_text = text if text.endswith(("\n", "\r")) else text + "\n"
        session.shell.send(send_text)
        self._history.record(name, "input", text)
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
            if pattern in session.output_text():
                return {"matched": True, "cursor": session.cursor}
            await asyncio.sleep(0.1)
        return {"matched": False, "cursor": session.cursor}

    def search(self, name: str, query: str) -> dict:
        session = self._sessions.get(name)
        if session:
            return {"matches": session.search_output(query)}
        return self._history.search(name, query)

    def set_env(self, name: str, key: str, value: str) -> dict:
        session = self.get(name)
        _validate_env_key(key)
        self._history.set_session_env(name, key, value)
        session.shell.sendline(f"export {key}={shlex.quote(value)}")
        session.updated_at = datetime.now(timezone.utc)
        return self.get_profile(name)

    def unset_env(self, name: str, key: str) -> dict:
        session = self.get(name)
        _validate_env_key(key)
        self._history.unset_session_env(name, key)
        session.shell.sendline(f"unset {key}")
        session.updated_at = datetime.now(timezone.utc)
        return self.get_profile(name)

    def set_startup_commands(self, name: str, commands: list[str]) -> dict:
        self._history.set_session_startup_commands(name, commands)
        return self.get_profile(name)

    def run_startup_commands(self, name: str, commands: list[str] | None = None) -> None:
        session = self.get(name)
        profile = self.get_profile(name)
        to_run = list(commands if commands is not None else profile["startup_commands"])
        for command in to_run:
            if not command.strip():
                continue
            session.shell.send(command if command.endswith(("\n", "\r")) else command + "\n")
            self._history.record(name, "input", command)
        session.updated_at = datetime.now(timezone.utc)

    def _apply_workspace_to_session(self, session: TerminalSession, workspace: dict) -> None:
        for key, value in workspace["env"].items():
            session.shell.sendline(f"export {key}={shlex.quote(str(value))}")
        for command in workspace["startup_commands"]:
            if command.strip():
                session.shell.send(command if command.endswith(("\n", "\r")) else command + "\n")
                self._history.record(session.id, "input", command)
        session.updated_at = datetime.now(timezone.utc)

    def add_alert(self, scope: str, pattern: str, terminal_id: str | None = None, label: str | None = None) -> dict:
        if scope == "session" and not terminal_id:
            raise ValueError("terminal_id is required for session alerts")
        if scope == "global":
            terminal_id = None
        return self._history.add_alert(scope, pattern, terminal_id, label)

    def list_alerts(self, scope: str | None = None, terminal_id: str | None = None) -> list[dict]:
        return self._history.list_alerts(scope, terminal_id)

    def remove_alert(self, alert_id: str) -> bool:
        return self._history.remove_alert(alert_id)

    def list_alert_events(self, terminal_id: str | None = None, since: int = 0) -> list[dict]:
        return self._history.list_alert_events(terminal_id, since)

    def add_checkpoint(self, name: str, label: str, note: str | None = None, cursor: int | None = None) -> dict:
        session = self.get(name)
        return self._history.add_bookmark(name, session.cursor if cursor is None else cursor, label, note)

    def list_checkpoints(self, name: str | None = None) -> list[dict]:
        return self._history.list_bookmarks(name)

    def remove_checkpoint(self, checkpoint_id: str) -> bool:
        return self._history.remove_bookmark(checkpoint_id)

    def export_session(self, name: str) -> dict:
        session = self._sessions.get(name)
        profile = self.get_profile(name)
        history = self.get_history(name, 0)
        workspace_ids = self._history.list_workspace_ids_for_terminal(name)
        data = {
            "terminal_id": name,
            "profile": profile,
            "history": history,
            "alerts": self.list_alerts("session", name),
            "checkpoints": self.list_checkpoints(name),
            "workspaces": workspace_ids,
            "workspace_profiles": [self._history.get_workspace(workspace_id) for workspace_id in workspace_ids],
        }
        if session:
            data["status"] = self.status(name)
        else:
            data["status"] = self._history.status(name)
        return data

    async def import_session(self, snapshot: dict, terminal_id: str | None = None) -> dict:
        source_id = snapshot.get("terminal_id") or "session"
        target_id = terminal_id or f"{source_id}-restored"
        if target_id in self._sessions:
            raise ValueError(f"Terminal '{target_id}' already exists")
        profile = snapshot.get("profile") or {}
        env = dict(profile.get("env") or {})
        startup_commands = list(profile.get("startup_commands") or [])
        session = await self.create(target_id, env=env, startup_commands=None, run_startup_commands=False)
        events = (snapshot.get("history") or {}).get("events", [])
        for event in events:
            if event.get("type") == "input":
                self.send(target_id, event.get("text", ""))
                await asyncio.sleep(0.05)
        if startup_commands:
            self._history.set_session_startup_commands(target_id, startup_commands)
        for checkpoint in snapshot.get("checkpoints", []):
            self._history.add_bookmark(
                target_id,
                int(checkpoint.get("cursor", session.cursor)),
                str(checkpoint.get("label", "checkpoint")),
                checkpoint.get("note"),
            )
        for alert in snapshot.get("alerts", []):
            if alert.get("scope") == "session":
                self.add_alert("session", str(alert.get("pattern", "")), target_id, alert.get("label"))
        workspace_snapshots = snapshot.get("workspace_profiles") or []
        if workspace_snapshots:
            for workspace in workspace_snapshots:
                workspace_id = str(workspace.get("id", "")).strip()
                if not workspace_id:
                    continue
                try:
                    self._history.get_workspace(workspace_id)
                except KeyError:
                    self._history.create_workspace(
                        workspace_id,
                        dict(workspace.get("env") or {}),
                        list(workspace.get("startup_commands") or []),
                    )
                self._history.add_workspace_member(workspace_id, target_id)
                self.apply_workspace(workspace_id, target_id)
        else:
            for workspace_id in snapshot.get("workspaces", []):
                try:
                    self._history.get_workspace(workspace_id)
                    self._history.add_workspace_member(workspace_id, target_id)
                    self.apply_workspace(workspace_id, target_id)
                except KeyError:
                    continue
        return {"terminal_id": session.id, "status": "imported"}

    def health(self, stale_after_seconds: int = 300) -> dict:
        return self._history.health(self._sessions, stale_after_seconds)

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
        self._history.close()
