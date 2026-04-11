"""Optional progress hook for long-running nodes (search, lit review).

Set by run_pipeline when event_callback is provided so work inside a single
graph node can still stream updates to SSE clients.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional

_cb: Optional[Callable[[str], None]] = None
_lock = threading.Lock()


def set_progress_callback(cb: Optional[Callable[[str], None]]) -> None:
    global _cb
    with _lock:
        _cb = cb


def emit_progress(message: str) -> None:
    with _lock:
        cb = _cb
    if not cb:
        return
    try:
        cb(message)
    except Exception:
        pass
