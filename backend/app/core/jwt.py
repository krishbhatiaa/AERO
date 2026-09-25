"""JWT validation utilities with JWKS support."""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
import jwt
from jwt import InvalidTokenError

log = logging.getLogger("app.jwt")

_jwks_cache: dict[str, Any] = {"keys": {}, "ts": 0.0}
_JWKS_TTL = 3600.0
_jwks_lock = __import__("threading").Lock()

SUPPORTED_ALGORITHMS = ["RS256", "ES256"]


def fetch_jwks(url: str) -> dict[str, Any]:
    now = time.monotonic()
    with _jwks_lock:
        if _jwks_cache["keys"] and (now - _jwks_cache["ts"]) < _JWKS_TTL:
            return _jwks_cache["keys"]
    try:
        resp = httpx.get(url, timeout=10.0)
        resp.raise_for_status()
        data = resp.json()
        with _jwks_lock:
            _jwks_cache["keys"] = data
            _jwks_cache["ts"] = now
        return data
    except Exception:
        log.warning("jwks_fetch_failed", extra={"url": url})
        with _jwks_lock:
            if _jwks_cache["keys"]:
                return _jwks_cache["keys"]
        raise


def _get_signing_key(jwks_url: str, kid: str) -> Any:
    jwks = fetch_jwks(jwks_url)
    for key_data in jwks.get("keys", []):
        if key_data.get("kid") == kid:
            return jwt.algorithms.RSAAlgorithm.from_jwk(key_data) if key_data.get("kty") == "RSA" else jwt.algorithms.ECAlgorithm.from_jwk(key_data)
    raise ValueError(f"No matching key found for kid={kid}")


def validate_jwt(token: str, issuer: str, audience: str, jwks_url: str) -> dict[str, Any]:
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        kid = unverified.get("kid", "")
        if not kid:
            raise ValueError("Token missing kid header")
        key = _get_signing_key(jwks_url, kid)
        alg = unverified.get("alg", "RS256")
        if alg not in SUPPORTED_ALGORITHMS:
            raise ValueError(f"Unsupported algorithm: {alg}")
        payload = jwt.decode(token, key, algorithms=[alg], issuer=issuer, audience=audience, options={"require": ["exp", "iss", "aud"]})
        return payload
    except InvalidTokenError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc


def decode_jwt_claims(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except InvalidTokenError:
        return {}


def discover_oidc_urls(issuer_url: str) -> dict[str, str]:
    discovery_url = issuer_url.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp = httpx.get(discovery_url, timeout=10.0)
        resp.raise_for_status()
        config = resp.json()
        return {"jwks_uri": config.get("jwks_uri", ""), "issuer": config.get("issuer", issuer_url)}
    except Exception:
        log.warning("oidc_discovery_failed", extra={"issuer": issuer_url})
        return {"jwks_uri": "", "issuer": issuer_url}


def extract_roles(claims: dict[str, Any], role_claim: str = "role") -> list[str]:
    raw = claims.get(role_claim, [])
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list):
        return [str(r) for r in raw]
    return []


OIDC_ROLE_MAP = {"admin": "admin", "analyst": "analyst", "viewer": "viewer"}


def map_oidc_role(oidc_roles: list[str], role_claim: str = "role") -> str:
    for role in reversed(oidc_roles):
        mapped = OIDC_ROLE_MAP.get(role.lower())
        if mapped:
            return mapped
    return "viewer"
