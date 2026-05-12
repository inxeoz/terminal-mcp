import signal as _signal

SIGNAL_MAP: dict[str, int] = {
    "SIGINT": _signal.SIGINT,
    "SIGTERM": _signal.SIGTERM,
    "SIGKILL": _signal.SIGKILL,
}


def send_signal(session, sig: str) -> bool:
    if sig not in SIGNAL_MAP:
        return False
    try:
        session.shell.kill(SIGNAL_MAP[sig])
        return True
    except Exception:
        return False
