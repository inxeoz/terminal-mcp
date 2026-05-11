import asyncio

import pexpect

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
        except pexpect.exceptions.TIMEOUT:
            pass
        except pexpect.exceptions.EOF as exc:
            session.alive = False
            message = f"reader EOF for '{session.id}': {exc}"
            log(message, "TERM")
            if session.on_error:
                session.on_error(message)
            break
        except Exception as exc:
            session.alive = False
            message = f"reader error for '{session.id}': {exc}"
            log(message, "TERM")
            if session.on_error:
                session.on_error(message)
            break
        await asyncio.sleep(0.05)
    log(f"reader stopped for '{session.id}'", "TERM")
