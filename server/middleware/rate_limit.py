"""
Simple in-memory tenant-aware rate limiter.
"""

from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, status

from server.config.settings import get_settings


class TenantRateLimiter:
    """Token-bucket style limiter scoped per tenant."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, Deque[float]] = {}
        self._lock = Lock()

    def check(self, tenant_id: str) -> Tuple[bool, float]:
        """
        Record a tenant request if allowed.

        Returns:
            Tuple[bool, float]: (allowed, seconds_until_reset)
        """
        now = time.time()
        with self._lock:
            queue = self._requests.setdefault(tenant_id, deque())
            while queue and now - queue[0] >= self.window_seconds:
                queue.popleft()

            if len(queue) >= self.max_requests:
                retry_after = self.window_seconds - (now - queue[0])
                return False, max(retry_after, 0.0)

            queue.append(now)
            return True, 0.0


def get_rate_limiter() -> TenantRateLimiter:
    """Return a singleton rate limiter configured via settings."""
    settings = get_settings()
    max_requests = settings.rate_limit_requests_per_minute
    window_seconds = 60
    # Cache the limiter on the function to avoid multiple instances
    if not hasattr(get_rate_limiter, "_limiter"):
        get_rate_limiter._limiter = TenantRateLimiter(max_requests, window_seconds)  # type: ignore[attr-defined]
    return get_rate_limiter._limiter  # type: ignore[attr-defined]


def enforce_rate_limit(tenant_id: str) -> None:
    """Raise HTTP 429 if the tenant exceeds the configured request rate."""
    limiter = get_rate_limiter()
    allowed, retry_after = limiter.check(tenant_id)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for tenant.",
            headers={"Retry-After": str(int(retry_after))},
        )
