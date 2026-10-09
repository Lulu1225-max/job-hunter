from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings
from app.core.runtime_logging import get_server_logger


bearer_scheme = HTTPBearer(auto_error=False)
logger = get_server_logger()
SUPABASE_AUTH_MAX_ATTEMPTS = 3
SUPABASE_AUTH_RETRY_BASE_SECONDS = 0.2


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None = None
    claims: dict[str, Any] | None = None


class AuthError(Exception):
    pass


class AuthNetworkError(AuthError):
    pass


def _supabase_auth_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(15.0, connect=5.0, read=15.0, write=10.0, pool=5.0),
        follow_redirects=False,
        limits=httpx.Limits(max_connections=5, max_keepalive_connections=0),
        trust_env=False,
    )


def _log_auth_request(*, auth_stage: str, endpoint_type: str, attempt: int, error_type: str) -> None:
    logger.warning(
        "auth_request_event %s",
        json.dumps({
            "auth_stage": auth_stage,
            "endpoint_type": endpoint_type,
            "attempt": attempt,
            "error_type": error_type,
        }, separators=(",", ":")),
    )


def _issuer() -> str | None:
    if not settings.supabase_url:
        return None
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _jwks_url() -> str | None:
    issuer = _issuer()
    if not issuer:
        return None
    return f"{issuer}/.well-known/jwks.json"


def _decode_with_jwks(token: str) -> dict[str, Any]:
    jwks_url = _jwks_url()
    issuer = _issuer()
    if not jwks_url or not issuer:
        raise AuthError("Supabase URL is not configured")
    signing_key = PyJWKClient(jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=settings.supabase_jwt_audience,
        issuer=issuer,
        options={"require": ["sub", "aud", "iss", "exp"]},
    )


def _decode_with_legacy_secret(token: str) -> dict[str, Any]:
    issuer = _issuer()
    if not settings.supabase_jwt_secret or not issuer:
        raise AuthError("Supabase legacy JWT secret is not configured")
    return jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=["HS256"],
        audience=settings.supabase_jwt_audience,
        issuer=issuer,
        options={"require": ["sub", "aud", "iss", "exp"]},
    )


def _verify_with_auth_server(token: str) -> dict[str, Any]:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise AuthError("Supabase URL or publishable key is not configured")
    response = httpx.get(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
        headers={
            "apikey": settings.supabase_publishable_key,
            "Authorization": f"Bearer {token}",
        },
        timeout=10,
    )
    if response.status_code != 200:
        raise AuthError("Supabase rejected the access token")
    user = response.json()
    return {
        "sub": user.get("id"),
        "email": user.get("email"),
        "role": "authenticated",
    }


def authenticate_supabase_password(email: str, password: str) -> dict[str, Any]:
    if not settings.supabase_url or not settings.supabase_publishable_key:
        raise AuthError("Supabase URL or publishable key is not configured")
    endpoint = f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    response: httpx.Response | None = None
    for attempt in range(1, SUPABASE_AUTH_MAX_ATTEMPTS + 1):
        try:
            with _supabase_auth_client() as client:
                response = client.post(
                    endpoint,
                    headers={
                        "apikey": settings.supabase_publishable_key,
                        "Content-Type": "application/json",
                    },
                    json={"email": email, "password": password},
                )
            break
        except (httpx.NetworkError, httpx.TimeoutException, httpx.RemoteProtocolError) as exc:
            _log_auth_request(
                auth_stage="supabase_password_auth",
                endpoint_type="token_password_grant",
                attempt=attempt,
                error_type=type(exc).__name__,
            )
            if attempt == SUPABASE_AUTH_MAX_ATTEMPTS:
                raise AuthNetworkError("Supabase authentication network request failed") from exc
            time.sleep(SUPABASE_AUTH_RETRY_BASE_SECONDS * (2 ** (attempt - 1)))
    if response is None:
        raise AuthNetworkError("Supabase authentication network request failed")
    if response.status_code != 200:
        _log_auth_request(
            auth_stage="supabase_password_auth",
            endpoint_type="token_password_grant",
            attempt=attempt,
            error_type=f"HTTPStatus{response.status_code}",
        )
        raise AuthError("Supabase password authentication failed")
    session = response.json()
    user_id = session.get("user", {}).get("id")
    if not user_id:
        raise AuthError("Supabase session is missing user.id")
    UUID(str(user_id))
    return session


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    errors: list[str] = []
    for verifier in (_decode_with_jwks, _decode_with_legacy_secret, _verify_with_auth_server):
        try:
            claims = verifier(token)
            subject = claims.get("sub")
            if not subject:
                raise AuthError("Verified token is missing sub")
            UUID(str(subject))
            return claims
        except Exception as exc:
            errors.append(str(exc))
    raise AuthError("; ".join(errors))


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedUser:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "AUTH_REQUIRED", "message": "Authentication required"}},
        )
    try:
        claims = verify_supabase_jwt(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": "INVALID_TOKEN", "message": "Invalid authentication token"}},
        ) from exc
    user = AuthenticatedUser(id=UUID(str(claims["sub"])), email=claims.get("email"), claims=claims)
    request.state.current_user = user
    return user


def get_current_user_id(current_user: AuthenticatedUser = Depends(get_current_user)) -> UUID:
    return current_user.id
