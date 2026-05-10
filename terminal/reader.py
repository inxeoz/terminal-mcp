import asyncio

from terminal.log import log


async def reader_loop(session):
    shell = session.shell
    log(f"reader started for '{session.id}'", "TERM")
    while session.alive:
        try:
            if not shell.isalive():
                session.alive = False
                log(f"shell '{session.id}' exited (rc={shell.exitstatus})", "TERM")
                break
            data = shell.read_nonblocking(size=4096, timeout=0)
            if data:
                session.append_output(data)
        except Exception:
            pass
        await asyncio.sleep(0.05)
    log(f"reader stopped for '{session.id}'", "TERM")
