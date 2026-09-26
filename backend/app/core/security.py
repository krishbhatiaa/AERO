"""Authentication/authorisation hooks, rate limiting, body-size limits and secure headers.

Auth modes (``AUTH_MODE``):
* ``none``     local development only: every caller is the ``local-dev`` principal with role ``admin``.
* ``api_key``  ``X-API-Key`` header checked against ``API_KEYS`` (``name:role:sha256hex`` entries). Keys are stored
               only as SHA-256 digests and compared in constant time.
* ``oidc``     Bearer JWT token validated against OIDC provider (JWKS).
Roles are ordered ``viewer < analyst < admin``.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

from app.core.config import Settings
from app.core.errors import ApiError, problem
from app.core.jwt import decode_jwt_claims, discover_oidc_urls, extract_roles, map_oidc_role, validate_jwt
from fastapi import Depends, Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

log = logging.getLogger("app.security")

ROLES = ("viewer", "analyst", "admin")


@dataclass(frozen=True)
class Principal:
    name: str
    role: str
    source: str = "api_key"

    def has(self, minimum: str) -> bool:
        return ROLES.index(self.role) >= ROLES.index(minimum)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def parse_api_keys(raw: str) -> dict[str, Principal]:
    """``name:role:sha256hex`` entries, comma separated -> ``{digest: Principal}``."""
    out: dict[str, Principal] = {}
    for entry in filter(None, (e.strip() for e in raw.split(","))):
        try:
            name, role, digest = entry.split(":")
        except ValueError as exc:
            raise ValueError("API_KEYS entries must look like name:role:sha256hex") from exc
        if role not in ROLES or len(digest) != 64:
            raise ValueError(f"API_KEYS entry for '{name}' has an invalid role or digest")
        out[digest.lower()] = Principal(name, role, "api_key")
    return out


def authenticate_oidc(settings: Settings, token: str) -> Principal | None:
    try:
        issuer = settings.oidc_issuer_url
        audience = settings.oidc_audience or settings.oidc_client_id
        jwks_url = settings.oidc_jwks_url
        if not jwks_url and issuer:
            discovered = discover_oidc_urls(issuer)
            jwks_url = discovered.get("jwks_url") or jwks_url
            issuer = discovered.get("issuer") or issuer
        if not jwks_url or not issuer:
            log.warning("oidc_config_incomplete")
            return None
        claims = validate_jwt(token, issuer, audience, jwks_url)
        sub = claims.get("sub", "unknown")
        email = claims.get("email", sub)
        oidc_roles = extract_roles(claims, settings.oidc_role_claim)
        role = map_oidc_role(oidc_roles, settings.oidc_role_claim)
        return Principal(name=email, role=role, source="oidc")
    except Exception:
        log.debug("oidc_validation_failed", exc_info=True)
        return None


def authenticate_key(settings: Settings, key: str | None) -> Principal | None:
    if settings.auth_mode == "none":
        return Principal("local-dev", "admin", "none")
    if not key:
        return None
    digest = hash_api_key(key)
    for known, principal in parse_api_keys(settings.api_keys.get_secret_value()).items():
        if hmac.compare_digest(known, digest):
            return principal
    return None


def get_principal(request: Request) -> Principal:
    """FastAPI dependency: resolve the caller or raise 401."""
    settings: Settings = request.app.state.settings
    auth_header = request.headers.get("Authorization", "")
    if settings.auth_mode == "oidc" and auth_header.startswith("Bearer "):
        token = auth_header[7:]
        p = authenticate_oidc(settings, token)
        if p is not None:
            request.state.principal = p
            return p
    p = authenticate_key(settings, request.headers.get("X-API-Key"))
    if p is None:
        request.app.state.audit.record("auth.failed", "unknown", "denied", path=request.url.path)
        if settings.auth_mode == "oidc":
            raise ApiError(401, "AUTH_REQUIRED", "Authentication required", "Provide a valid X-API-Key or Bearer token.",
                           headers={"WWW-Authenticate": 'Bearer realm="api", error="invalid_token"'})
        raise ApiError(401, "AUTH_REQUIRED", "Authentication required", "Provide a valid X-API-Key header.",
                       headers={"WWW-Authenticate": "ApiKey"})
    request.state.principal = p
    return p


def require_role(minimum: str):  # noqa: ANN201 - returns a dependency callable
    def dep(request: Request, principal: Principal = Depends(get_principal)) -> Principal:
        if not principal.has(minimum):
            request.app.state.audit.record("authz.denied", principal.name, "denied", required=minimum, path=request.url.path)
            raise ApiError(403, "FORBIDDEN", "Insufficient role", f"This operation needs role '{minimum}' or higher.")
        return principal

    return dep


class RateLimiter:
    """Per-client sliding-window limiter (in-process). Multi-worker deployments need the Redis-backed variant."""

    def __init__(self, per_minute: int, window_s: float = 60.0) -> None:
        self.limit, self.window = per_minute, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Return ``(allowed, retry_after_seconds)``."""
        t = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and t - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (t - q[0])) + 1)
            q.append(t)
            return True, 0


EXEMPT_PATHS = ("/api/v1/live", "/api/v1/health", "/api/v1/ready")


class RateLimitMiddleware:
    """ASGI middleware applying :class:`RateLimiter` to HTTP requests (health probes exempt)."""

    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        self.app, self.limiter = app, limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in EXEMPT_PATHS or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        client = headers.get(b"x-api-key")
        who = "key:" + hash_api_key(client.decode("latin-1"))[:12] if client else "ip:" + (scope.get("client") or ("?", 0))[0]
        ok, retry = self.limiter.check(who)
        if not ok:
            resp = problem(429, "RATE_LIMITED", "Too many requests", "Rate limit exceeded; retry later.",
                           headers={"Retry-After": str(retry)})
            await resp(scope, receive, send)
            return
        await self.app(scope, receive, send)


class BodyLimitMiddleware:
    """Rejects request bodies larger than ``max_bytes`` (Content-Length fast path + streaming counter)."""

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app, self.max = app, max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        length = dict(scope.get("headers") or []).get(b"content-length")
        too_big = problem(413, "BODY_TOO_LARGE", "Request body too large", f"Maximum body size is {self.max} bytes.")
        if length is not None and length.isdigit() and int(length) > self.max:
            await too_big(scope, receive, send)
            return
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            msg = await receive()
            if msg["type"] == "http.request":
                seen += len(msg.get("body", b""))
                if seen > self.max:
                    raise ApiError(413, "BODY_TOO_LARGE", "Request body too large", f"Maximum body size is {self.max} bytes.")
            return msg

        await self.app(scope, limited, send)


class RequestTimeoutMiddleware:
    """Enforces a maximum request processing time."""

    def __init__(self, app: ASGIApp, timeout: int) -> None:
        self.app, self.timeout = app, timeout

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        timeout = 600 if scope.get("path", "").endswith("/fetch-era5") else self.timeout
        try:
            await asyncio.wait_for(self.app(scope, receive, send), timeout=timeout)
        except asyncio.TimeoutError:
            resp = problem(504, "REQUEST_TIMEOUT", "Request timed out", f"Server did not respond within {timeout}s.")
            await resp(scope, receive, send)


class ConcurrencyLimitMiddleware:
    """Limits concurrent in-flight requests."""

    def __init__(self, app: ASGIApp, max_concurrent: int) -> None:
        self.app = app
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            await self.app(scope, receive, send)
            return
        async with self._semaphore:
            await self.app(scope, receive, send)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "Cross-Origin-Resource-Policy": "same-site",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
