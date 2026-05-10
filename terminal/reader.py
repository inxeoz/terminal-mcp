import asyncio


async def reader_loop(session):
    shell = session.shell
    while session.alive:
        try:
            if not shell.isalive():
                session.alive = False
                break
            data = shell.read_nonblocking(size=4096, timeout=0)
            if data:
                session.append_output(data)
        except Exception:
            pass
        await asyncio.sleep(0.05)
