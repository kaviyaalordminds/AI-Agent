"""Lightweight, DB-free rate limiter for auth-sensitive endpoints.

Uses an in-process sliding window keyed by (bucket, identifier). This is
sufficient for a single-process deployment; a multi-instance production
deployment should back this with Redis (swap the store below — the
`is_allowed` call-site contract stays the same).
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def is_allowed(key: str, max_requests: int, window_seconds: int) -> bool:
    now = time.monotonic()
    with _lock:
        window = _buckets[key]
        while window and now - window[0] > window_seconds:
            window.popleft()
        if len(window) >= max_requests:
            return False
        window.append(now)
        return True


def enforce_rate_limit(request: Request, bucket: str, max_requests: int | None = None) -> None:
    ip = request.client.host if request.client else "unknown"
    key = f"{bucket}:{ip}"
    allowed = is_allowed(
        key,
        max_requests or settings.rate_limit_max_requests,
        settings.rate_limit_window_minutes * 60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
        )
