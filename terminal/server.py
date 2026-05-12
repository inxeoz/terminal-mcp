import asyncio
import json
import os
import signal
import socket
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from terminal.manager import SessionManager
from terminal.tools import TOOLS
from terminal.web import create_app
from terminal.log import log

app = Server("i4z-terminal-mcp")
manager = SessionManager()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    log(f"{name}({_fmt_args(arguments)})", "MCP")
    try:
        result = await _handle_tool(name, arguments)
        summary = _fmt_result(name, result)
        log(f"  -> {summary}", "MCP")
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except KeyError as e:
        log(f"  -> ERROR: {e}", "MCP")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except ValueError as e:
        log(f"  -> ERROR: {e}", "MCP")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except RuntimeError as e:
        log(f"  -> ERROR: {e}", "MCP")
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


def _fmt_args(args: dict) -> str:
    parts = []
    for k, v in args.items():
        s = str(v)
        if len(s) > 80:
            s = s[:77] + "..."
        parts.append(f"{k}={s!r}")
    return ", ".join(parts)


def _fmt_result(name: str, result: dict) -> str:
    if name == "create_terminal":
        return f"terminal_id={result.get('terminal_id', '?')}"
    if name in ("terminal_profile", "configure_terminal"):
        return "profile updated"
    if name == "list_terminals":
        return f"{len(result)} terminals"
    if name == "send_input":
        return "OK"
    if name == "read_output":
        size = len(result.get("output", ""))
        return f"{size} bytes, cursor={result.get('cursor', 0)}"
    if name == "terminal_status":
        return f"pid={result.get('pid')}, alive={result.get('alive')}"
    if name in ("wait_for_output", "search_output"):
        return f"matched={result.get('matched')}" if "matched" in result else f"{len(result.get('matches', []))} matches"
    if name == "add_output_alert":
        return f"alert_id={result.get('id', '?')}"
    if name == "list_output_alerts":
        return f"{len(result)} alerts"
    if name == "list_alert_events":
        return f"{len(result)} alert events"
    if name == "add_checkpoint":
        return f"checkpoint_id={result.get('id', '?')}"
    if name == "list_checkpoints":
        return f"{len(result)} checkpoints"
    if name == "remove_checkpoint":
        return f"removed={result.get('removed', False)}"
    if name in ("export_session", "import_session"):
        return result.get("terminal_id", "") or "OK"
    if name == "health_report":
        counts = result.get("counts", {})
        return f"db_ok={result.get('db', {}).get('ok', False)}, alerts={counts.get('alerts', 0)}, workspaces={counts.get('workspaces', 0)}, stale={len(result.get('sessions', {}).get('stale', []))}"
    if name == "create_workspace":
        return f"workspace_id={result.get('id', '?')}"
    if name == "list_workspaces":
        return f"{len(result)} workspaces"
    if name == "workspace_status":
        return f"{len(result.get('members', []))} members"
    if name in ("configure_workspace", "add_terminal_to_workspace", "remove_terminal_from_workspace", "apply_workspace"):
        return "workspace updated"
    if name == "web_url":
        return result.get("url", "")
    return "OK"


async def _handle_tool(name: str, args: dict) -> dict:
    if name == "create_terminal":
        session = await manager.create(args["name"], args.get("env"), args.get("startup_commands"), args.get("workspace_id"))
        log(f"terminal '{session.id}' created, pid={session.get_pid()}", "TERM")
        return {"terminal_id": session.id, "status": "created"}

    if name == "list_terminals":
        return manager.list_all()

    if name == "terminal_status":
        return manager.status(args["terminal_id"])

    if name == "terminal_profile":
        return manager.get_profile(args["terminal_id"])

    if name == "configure_terminal":
        terminal_id = args["terminal_id"]
        set_env = args.get("set_env") or {}
        unset_env = args.get("unset_env") or []
        startup_commands = args.get("startup_commands")
        result = manager.get_profile(terminal_id)
        for key, value in set_env.items():
            result = manager.set_env(terminal_id, key, str(value))
        for key in unset_env:
            result = manager.unset_env(terminal_id, key)
        if startup_commands is not None:
            result = manager.set_startup_commands(terminal_id, [str(cmd) for cmd in startup_commands])
        if args.get("run_startup_commands"):
            manager.run_startup_commands(terminal_id, [str(cmd) for cmd in startup_commands] if startup_commands is not None else None)
            result = manager.get_profile(terminal_id)
        return result

    if name == "send_input":
        manager.send(args["terminal_id"], args["text"])
        short = args["text"].strip()[:60]
        tid = args["terminal_id"]
        log(f"'{tid}' <- {short}", "TERM")
        return {"status": "sent"}

    if name == "read_output":
        max_bytes = args.get("max_bytes")
        if max_bytes is not None:
            max_bytes = int(max_bytes)
        return manager.read(args["terminal_id"], args.get("since", 0), max_bytes)

    if name == "send_signal":
        manager.signal(args["terminal_id"], args["signal"])
        return {"status": "signaled"}

    if name == "kill_terminal":
        tid = args["terminal_id"]
        await manager.kill(tid)
        log(f"terminal '{tid}' killed", "TERM")
        return {"status": "killed"}

    if name == "wait_for_output":
        return await manager.wait_for(
            args["terminal_id"],
            args["pattern"],
            float(args.get("timeout", 30)),
        )

    if name == "search_output":
        return manager.search(args["terminal_id"], args["query"])

    if name == "add_output_alert":
        return manager.add_alert(
            args["scope"],
            args["pattern"],
            args.get("terminal_id"),
            args.get("label"),
        )

    if name == "list_output_alerts":
        return manager.list_alerts(args.get("scope"), args.get("terminal_id"))

    if name == "remove_output_alert":
        removed = manager.remove_alert(args["alert_id"])
        return {"removed": removed, "alert_id": args["alert_id"]}

    if name == "list_alert_events":
        return manager.list_alert_events(args.get("terminal_id"), int(args.get("since", 0)))

    if name == "health_report":
        return manager.health()

    if name == "create_workspace":
        return manager.create_workspace(args["workspace_id"], args.get("env"), args.get("startup_commands"))

    if name == "list_workspaces":
        return manager.list_workspaces()

    if name == "workspace_status":
        return manager.workspace_status(args["workspace_id"])

    if name == "configure_workspace":
        return manager.configure_workspace(
            args["workspace_id"],
            args.get("set_env"),
            args.get("unset_env"),
            args.get("startup_commands"),
            bool(args.get("apply_to_members", True)),
        )

    if name == "add_terminal_to_workspace":
        return manager.add_terminal_to_workspace(args["workspace_id"], args["terminal_id"])

    if name == "remove_terminal_from_workspace":
        return manager.remove_terminal_from_workspace(args["workspace_id"], args["terminal_id"])

    if name == "apply_workspace":
        return manager.apply_workspace(args["workspace_id"], args.get("terminal_id"))

    if name == "add_checkpoint":
        return manager.add_checkpoint(
            args["terminal_id"],
            args["label"],
            args.get("note"),
            args.get("cursor"),
        )

    if name == "list_checkpoints":
        return manager.list_checkpoints(args.get("terminal_id"))

    if name == "remove_checkpoint":
        removed = manager.remove_checkpoint(args["checkpoint_id"])
        return {"removed": removed, "checkpoint_id": args["checkpoint_id"]}

    if name == "export_session":
        return manager.export_session(args["terminal_id"])

    if name == "import_session":
        return await manager.import_session(args["snapshot"], args.get("terminal_id"))

    if name == "web_url":
        return {"url": manager.web_url}

    if name == "rename_terminal":
        return manager.rename(args["terminal_id"], args["new_id"])

    if name == "resize_terminal":
        manager.resize(args["terminal_id"], int(args["rows"]), int(args["cols"]))
        return {"status": "resized", "terminal_id": args["terminal_id"], "rows": args["rows"], "cols": args["cols"]}

    raise ValueError(f"Unknown tool: {name}")


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _shutdown_requested = False

    def _on_signal():
        nonlocal _shutdown_requested
        if _shutdown_requested:
            print("\nForced exit", file=sys.stderr)
            loop.call_soon_threadsafe(lambda: sys.exit(1))
            return
        _shutdown_requested = True
        print("\nShutting down... (Ctrl+D to stop)", file=sys.stderr)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(_main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        try:
            loop.run_until_complete(manager.shutdown())
        except Exception:
            pass
        loop.close()
        print("i4z-terminal-mcp stopped", file=sys.stderr)


async def _main():
    web_port = int(os.environ.get("I4Z_TERMINAL_WEB_PORT", "0") or "0")
    if web_port == 0:
        web_port = _find_free_port()

    web_host = os.environ.get("I4Z_TERMINAL_WEB_HOST", "0.0.0.0")

    import uvicorn
    web_app = create_app(manager)
    web_config = uvicorn.Config(web_app, host=web_host, port=web_port, log_level="warning")
    web_server = uvicorn.Server(web_config)

    print(f"i4z-terminal-mcp running (Ctrl+D to stop)", file=sys.stderr)
    print(f"  Web UI: http://localhost:{web_port}", file=sys.stderr)
    manager.web_url = f"http://localhost:{web_port}"

    async with stdio_server() as (read, write):
        await asyncio.gather(
            app.run(read, write, app.create_initialization_options()),
            web_server.serve(),
            return_exceptions=True,
        )


if __name__ == "__main__":
    main()
