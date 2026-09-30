"""
throttle.py — limits repeated failed logins, so passwords can't be guessed
non-stop.

After LIMIT failures within WINDOW seconds, that email is locked for WINDOW
seconds. Each network address gets a higher limit (IP_LIMIT), so one person
can't lock out many accounts from one machine without also being stopped.
Counts are kept in memory, which is enough for a single local server; they
reset when the server restarts.
"""

from __future__ import annotations
import threading
import time
from collections import defaultdict, deque

LIMIT = 5               # failed attempts per email ...
IP_LIMIT = 20           # ... and per network address
WINDOW = 15 * 60        # within 15 minutes, then locked for 15 minutes

_fails: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def _keys(email: str, ip: str | None) -> list[tuple[str, int]]:
    return [(f"email:{email}", LIMIT)] + ([(f"ip:{ip}", IP_LIMIT)] if ip else [])


def _prune(q: deque, now: float) -> None:
    while q and now - q[0] > WINDOW:
        q.popleft()


def retry_after(email: str, ip: str | None) -> int:
    """Seconds until another attempt is allowed; 0 if allowed now."""
    now = time.monotonic()
    with _lock:
        wait = 0.0
        for key, limit in _keys(email, ip):
            q = _fails[key]
            _prune(q, now)
            if len(q) >= limit:
                wait = max(wait, WINDOW - (now - q[-limit]))
        return int(wait) + 1 if wait > 0 else 0


def failed(email: str, ip: str | None) -> None:
    now = time.monotonic()
    with _lock:
        for key, _ in _keys(email, ip):
            _fails[key].append(now)


def succeeded(email: str) -> None:
    with _lock:
        _fails.pop(f"email:{email}", None)
