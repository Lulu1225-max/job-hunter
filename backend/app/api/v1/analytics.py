from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import analytics_repo, ensure_user

router = APIRouter()


@router.get("/overview")
def overview(db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)) -> dict:
    ensure_user(db, user_id)
    return analytics_repo.overview(db, user_id)
