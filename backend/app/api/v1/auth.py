from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import AuthError, authenticate_supabase_password
from app.repositories.database import ensure_user

router = APIRouter()


@router.post("/demo")
def demo_login(db: Session = Depends(get_db)) -> dict:
    if not settings.demo_user_email or not settings.demo_user_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "DEMO_AUTH_NOT_CONFIGURED", "message": "Demo account is not configured"}},
        )
    try:
        session = authenticate_supabase_password(settings.demo_user_email, settings.demo_user_password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"error": {"code": "DEMO_AUTH_FAILED", "message": "Demo account authentication failed"}},
        ) from exc
    user = session.get("user", {})
    ensure_user(db, UUID(str(user["id"])), email=user.get("email"), display_name=user.get("user_metadata", {}).get("name"))
    return session
