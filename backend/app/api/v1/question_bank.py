from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user
from app.schemas.question_bank import FavoriteUpdate, QuestionBankCreate, QuestionBankUpdate
from app.services.question_bank_service import CATEGORIES, question_bank_service

router = APIRouter()


def missing(): return HTTPException(404, detail={"error": {"code": "QUESTION_BANK_ITEM_NOT_FOUND", "message": "Question Bank item not found"}})


@router.get("")
def list_items(search: str | None = None, category: str | None = None, favorite: bool | None = Query(None),
               db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    ensure_user(db, user_id)
    if category and category not in CATEGORIES: raise HTTPException(422, detail="Invalid category")
    return question_bank_service.list(db, user_id, search, category, favorite)


@router.post("")
def create_item(payload: QuestionBankCreate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    ensure_user(db, user_id)
    return question_bank_service.save(db, user_id, **payload.model_dump())


@router.patch("/{item_id}")
def update_item(item_id: UUID, payload: QuestionBankUpdate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    ensure_user(db, user_id)
    try: result = question_bank_service.update(db, user_id, item_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc: raise HTTPException(409, detail={"error": {"code": "DUPLICATE_QUESTION", "message": str(exc)}}) from exc
    if not result: raise missing()
    return result


@router.patch("/{item_id}/favorite")
def favorite_item(item_id: UUID, payload: FavoriteUpdate, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    ensure_user(db, user_id); result = question_bank_service.favorite(db, user_id, item_id, payload.is_favorite)
    if not result: raise missing()
    return result


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: UUID, db: Session = Depends(get_db), user_id: UUID = Depends(get_current_user_id)):
    ensure_user(db, user_id)
    if not question_bank_service.delete(db, user_id, item_id): raise missing()
    return Response(status_code=204)
