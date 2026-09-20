from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.security import get_current_user_id
from app.services.ai.client import _error_details, ai_client

router = APIRouter()


@router.get("/openai")
def openai_connectivity(_: UUID = Depends(get_current_user_id)):
    try:
        ai_client.check_responses_api()
        return {"ok": True, "model": settings.openai_model}
    except Exception as exc:
        details = _error_details(exc, "openai_connectivity_diagnostic", None)
        return JSONResponse(status_code=503, content={
            "ok": False,
            "exception_type": details["exception_type"],
            "status_code": details["status_code"],
            "openai_error_code": details["openai_error_code"],
            "openai_error_type": details["openai_error_type"],
            "safe_message": details["safe_message"],
        })
