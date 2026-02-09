"""API key and JWT authentication.

Uses a minimal HMAC-based JWT implementation (HS256 only) to avoid
heavy cryptography dependencies. For production with RS256, install
PyJWT or python-jose.
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from api.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def create_access_token(data: dict) -> str:
    """Create an HS256 JWT token."""
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = data.copy()
    payload["exp"] = int(time.time()) + (settings.jwt_expire_minutes * 60)
    payload["iat"] = int(time.time())
    body = _b64encode(json.dumps(payload).encode())
    sig_input = f"{header}.{body}".encode()
    sig = _b64encode(
        hmac.new(settings.jwt_secret.encode(), sig_input, hashlib.sha256).digest()
    )
    return f"{header}.{body}.{sig}"


def verify_jwt(token: str) -> dict:
    """Verify and decode an HS256 JWT token."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        header_b64, body_b64, sig_b64 = parts
        sig_input = f"{header_b64}.{body_b64}".encode()
        expected_sig = hmac.new(
            settings.jwt_secret.encode(), sig_input, hashlib.sha256
        ).digest()
        actual_sig = _b64decode(sig_b64)

        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid signature")

        payload = json.loads(_b64decode(body_b64))

        # Check expiration
        if payload.get("exp", 0) < time.time():
            raise ValueError("Token expired")

        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def require_auth(
    api_key: str | None = Security(api_key_header),
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> str:
    """Dependency that enforces authentication.

    Supports two methods:
    1. API key via X-API-Key header
    2. JWT Bearer token

    If settings.api_key is empty, auth is disabled (returns "anonymous").
    """
    # Auth disabled
    if not settings.api_key:
        return "anonymous"

    # Check API key
    if api_key and api_key == settings.api_key:
        return "api_key"

    # Check Bearer JWT
    if bearer:
        payload = verify_jwt(bearer.credentials)
        return payload.get("sub", "jwt_user")

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing or invalid authentication. Provide X-API-Key header or Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )
