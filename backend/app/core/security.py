from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings


bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    id: UUID
    email: str | None = None
    claims: dict[str, Any] | None = None


class AuthError(Exception):
    pass


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
    response = httpx.post(
        f"{settings.supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={
            "apikey": settings.supabase_publishable_key,
            "Content-Type": "application/json",
        },
        json={"email": email, "password": password},
        timeout=15,
    )
    if response.status_code != 200:
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
