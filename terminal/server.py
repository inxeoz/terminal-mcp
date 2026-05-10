import asyncio
import json
import signal
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from terminal.manager import SessionManager
from terminal.tools import TOOLS

app = Server("i4z-terminal-mcp")
manager = SessionManager()


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _handle_tool(name, arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except KeyError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except ValueError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
    except RuntimeError as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _handle_tool(name: str, args: dict) -> dict:
    if name == "create_terminal":
        session = await manager.create(args["name"])
        return {"terminal_id": session.id, "status": "created"}

    if name == "list_terminals":
        return manager.list_all()

    if name == "terminal_status":
        return manager.status(args["terminal_id"])

    if name == "send_input":
        manager.send(args["terminal_id"], args["text"])
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
        await manager.kill(args["terminal_id"])
        return {"status": "killed"}

    if name == "wait_for_output":
        return await manager.wait_for(
            args["terminal_id"],
            args["pattern"],
            float(args.get("timeout", 30)),
        )

    if name == "search_output":
        return manager.search(args["terminal_id"], args["query"])

    raise ValueError(f"Unknown tool: {name}")


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
    print("i4z-terminal-mcp running (Ctrl+D to stop)", file=sys.stderr)
    async with stdio_server() as (read, write):
        await app.run(read, write, app.create_initialization_options())


if __name__ == "__main__":
    main()
