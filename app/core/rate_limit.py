"""Centralized rate-limiting for the API (RF-COM-007).

Uses `slowapi` to apply per-IP request budgets. Default: 100 requests/minute
across all endpoints. Auth-heavy endpoints (login/register) are additionally
limited at 10/minute to deter credential stuffing.

Disable entirely by setting `RATE_LIMIT_ENABLED=false` in the environment.
"""
from __future__ import annotations

import os

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from fastapi import Request
from fastapi.responses import JSONResponse


def _enabled() -> bool:
    return os.environ.get("RATE_LIMIT_ENABLED", "true").lower() in ("1", "true", "yes")


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"] if _enabled() else [],
    headers_enabled=True,
)


AUTH_LIMIT = "10/minute" if _enabled() else ""
WRITE_LIMIT = "30/minute" if _enabled() else ""
READ_LIMIT = "100/minute" if _enabled() else ""


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Custom 429 response so the frontend gets a consistent error shape."""
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded: {exc.detail}"},
        headers={"Retry-After": str(getattr(exc, "retry_after", 60))},
    )
