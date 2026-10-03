"""Deployment hardening primitives: API-key auth, rate limiting, error hygiene.

All three are inert by default so local development remains friction-free:
- API auth activates as soon as API_KEY is set in the environment.
- Rate limits activate when clients hit the configured thresholds (limits
  themselves are configurable via RATE_LIMIT_* env vars, 0 disables).
- Error sanitization is always on for 5xx responses.
"""

import logging
import os
import re
import time
from collections import defaultdict, deque
from typing import Any

from fastapi import Header, HTTPException, Request, status

from app.config import settings

logger = logging.getLogger("intellinotes.security")

API_KEY_HEADER = "X-API-Key"

_MISSING_API_KEY_DETAIL = (
    "Missing or invalid API key. Send it in the '{}' header.".format(API_KEY_HEADER)
)


def require_api_key(
    x_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
) -> None:
    """FastAPI dependency enforcing a shared-secret header when configured.

    With no API_KEY in the environment this is a no-op, preserving the
    out-of-the-box local development experience.
    """
    if not settings.auth_enabled:
        return
    provided = (x_api_key or "").strip()
    if not provided or provided != settings.api_key.strip():
        logger.warning("Rejected request with missing/invalid API key.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_MISSING_API_KEY_DETAIL,
            headers={"WWW-Authenticate": "ApiKey"},
        )


class RateLimiter:
    """Minimal fixed-window per-identity limiter backed by an in-memory deque.

    Identity is the API key (when auth is on) or the client IP otherwise.
    Suitable for single-process deployments — the same constraint as the
    SQLite checkpointer and file-backed Chroma store, so it adds no new
    operational requirements.
    """

    def __init__(self, limit: int, window_seconds: float = 60.0):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, identity: str) -> None:
        """Raise 429 if `identity` exceeded the limit in the current window."""
        if self.limit <= 0:
            return
        now = time.monotonic()
        hits = self._hits[identity]
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = int(self.window - (now - hits[0])) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again shortly.",
                headers={"Retry-After": str(max(retry_after, 1))},
            )
        hits.append(now)

        # Opportunistic cleanup so idle identities don't pin memory forever.
        if len(self._hits) > 10_000:
            self._prune(now)

    def _prune(self, now: float) -> None:
        for key in [k for k, q in self._hits.items() if not q]:
            del self._hits[key]


def _limit_from_env(value: str, fallback: int) -> int:
    """Parse an env override like '30/minute'; return 0 to disable."""
    raw = os.environ.get(value, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw.split("/")[0])
    except (ValueError, IndexError):
        logger.warning("Unparseable rate limit %s=%r; using %d.", value, raw, fallback)
        return fallback


def make_chat_limiter() -> RateLimiter:
    return RateLimiter(_limit_from_env("RATE_LIMIT_CHAT", 10))


def make_upload_limiter() -> RateLimiter:
    return RateLimiter(_limit_from_env("RATE_LIMIT_UPLOAD", 5))


def client_identity(request: Request) -> str:
    """Best-effort caller identity behind proxies (Render/Railway set X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def sanitize_detail(exc: Exception) -> str:
    """Server-side log of the full error; client gets a generic 503 message."""
    logger.exception("Agent invocation failed: %s", exc)
    return "The agent could not process this request. Please try again later."


# --- Secret redaction for anything echoed back to clients (agent traces) ----

# Concrete, high-confidence credential shapes. Deliberately narrow so that
# ordinary content (quota messages, document text) is never mangled.
_SECRET_PATTERNS = (
    # Google API keys (e.g. leaked into an LLM error message)
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    # Tavily keys
    re.compile(r"tvly-[0-9A-Za-z]{16,}"),
    # JWT-shaped tokens
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    # Postgres/MySQL URLs with inline credentials
    re.compile(r"(postgres(ql)?|mysql)://[^\s:/@]+:[^\s/@]+@"),
    # key=value / key: value assignments for common credential labels
    re.compile(
        r"((?:api[_\-]?key|access[_\-]?token|refresh[_\-]?token|token|secret|password)"
        r"\s*[:=]\s*[\"']?)([^\s\"',;}]{6,})",
        re.IGNORECASE,
    ),
)

_REDACTED = "[REDACTED]"


def redact_secrets(value: Any) -> Any:
    """Recursively redact credential-shaped strings from response payloads.

    Applied to agent traces before they leave the API: if an LLM provider ever
    echoes a key (in an error message, for example) it must not reach the
    client, the UI, or the persisted conversation.
    """
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(
                lambda m: (m.group(1) + _REDACTED) if m.lastindex else _REDACTED,
                redacted,
            )
        return redacted
    if isinstance(value, dict):
        return {k: redact_secrets(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value
