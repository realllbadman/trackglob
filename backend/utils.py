import os
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from threading import Lock
from typing import Optional

from sqlalchemy.orm import Session

from .models import Shipment

TRACKING_PREFIX = (os.getenv("TRACKING_PREFIX") or "CX").strip().upper()
TRACKING_SUFFIX = (os.getenv("TRACKING_SUFFIX") or "").strip().upper()
try:
    TRACKING_DIGITS = max(4, min(20, int(os.getenv("TRACKING_DIGITS") or 10)))
except ValueError:
    TRACKING_DIGITS = 10


def format_tracking_number(digits: str) -> str:
    """PREFIX + digits + SUFFIX, e.g. WPC027063384444-CARGO."""
    return f"{TRACKING_PREFIX}{digits}{TRACKING_SUFFIX}"


def example_tracking_number() -> str:
    return format_tracking_number("0" * TRACKING_DIGITS)


def generate_tracking_number(db: Session) -> str:
    """PREFIX + N random digits + SUFFIX, unique in the shipments table."""
    for _ in range(50):
        tn = format_tracking_number("".join(str(secrets.randbelow(10)) for _ in range(TRACKING_DIGITS)))
        if not db.query(Shipment.id).filter(Shipment.tracking_number == tn).first():
            return tn
    return format_tracking_number(str(int(time.time() * 1000))[-TRACKING_DIGITS:].zfill(TRACKING_DIGITS))


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """SQLite returns naive datetimes; everything we store is UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    dt = as_utc(dt)
    return dt.isoformat().replace("+00:00", "Z") if dt else None


class RateLimiter:
    """Simple in-memory sliding-window counter, keyed per IP (per process)."""

    def __init__(self, max_hits: int, window_seconds: int):
        self.max_hits = max_hits
        self.window = window_seconds
        self._hits = defaultdict(deque)
        self._lock = Lock()

    def _prune(self, q: deque, now: float) -> None:
        while q and now - q[0] > self.window:
            q.popleft()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            return len(q) >= self.max_hits

    def hit(self, key: str) -> None:
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            self._prune(q, now)
            q.append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


def client_ip(request) -> str:
    # Don't read X-Forwarded-For here (clients could spoof it to dodge rate limits).
    # Behind nginx, uvicorn --proxy-headers --forwarded-allow-ips=127.0.0.1 sets client.host correctly.
    return request.client.host if request.client else "unknown"
