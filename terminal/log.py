import sys
from datetime import datetime, timezone


def log(msg: str, prefix: str = "") -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    label = f"[{prefix}] " if prefix else ""
    print(f"{ts}  {label}{msg}", file=sys.stderr, flush=True)
