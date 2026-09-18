from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user
from app.schemas.interviews import *
from app.services.interview_service import interview_service

router=APIRouter()
def fail(exc):
    if isinstance(exc,KeyError):raise HTTPException(404,detail={"error":{"code":"NOT_FOUND","message":str(exc).strip("'")}})
    if isinstance(exc,ValueError):raise HTTPException(422,detail={"error":{"code":"INVALID_INTERVIEW_REQUEST","message":str(exc)}})
    raise HTTPException(503,detail={"error":{"code":"AI_UNAVAILABLE","message":"Interview AI is temporarily unavailable"}})

@router.get("/interviews")
def list_interviews(db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id);return interview_service.list(db,user_id)
@router.post("/interviews")
def create_interview(payload:InterviewCreate,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.create_interview(db,user_id,payload.model_dump())
    except (KeyError,ValueError) as exc:return fail(exc)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(500,detail={"error":{"code":"INTERVIEW_SAVE_FAILED","message":"The interview could not be saved. Please try again."}})
@router.get("/interviews/{interview_id}")
def get_interview(interview_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.get_interview(db,user_id,interview_id)
    except Exception as exc:return fail(exc)
@router.patch("/interviews/{interview_id}")
def update_interview(interview_id:UUID,payload:InterviewUpdate,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id);result=interview_service.update_interview(db,user_id,interview_id,payload.model_dump(exclude_unset=True))
    if not result:raise HTTPException(404,detail="Interview not found")
    return result
@router.delete("/interviews/{interview_id}",status_code=204)
def delete_interview(interview_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    if not interview_service.delete_interview(db,user_id,interview_id):raise HTTPException(404,detail="Interview not found")
    return Response(status_code=204)
@router.post("/applications/{application_id}/interview-prep")
def prep(application_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.prep(db,user_id,application_id)
    except Exception as exc:return fail(exc)
@router.get("/interview/questions")
def questions(category:str|None=None,source:str|None=None,application_id:UUID|None=None,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id);return interview_service.questions(db,user_id,category,source,application_id)
@router.post("/interview/questions")
def add_question(payload:QuestionCreate,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.add_question(db,user_id,payload.model_dump())
    except Exception as exc:return fail(exc)
@router.post("/interview/questions/parse-preview")
def parse_questions(payload:ParseQuestionsRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.parse(db,user_id,payload.text)
    except Exception as exc:return fail(exc)
@router.post("/interview/questions/confirm")
def confirm_questions(payload:ConfirmQuestionsRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.confirm_questions(db,user_id,[item.model_dump() for item in payload.questions])
    except Exception as exc:return fail(exc)
@router.post("/interview/questions/generate")
def generate_questions(payload:GenerateQuestionsRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.generate_questions(db,user_id,payload.application_id,payload.category,payload.count)
    except Exception as exc:return fail(exc)
@router.post("/interview/questions/{question_id}/experiences")
def retrieve(question_id:UUID,payload:RetrieveForQuestionRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.retrieve(db,user_id,question_id,payload.limit)
    except Exception as exc:return fail(exc)
@router.post("/interview/questions/{question_id}/answers")
def answer(question_id:UUID,payload:GenerateAnswerRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.generate_answer(db,user_id,question_id,payload.experience_id,payload.answer_length,payload.regenerate)
    except Exception as exc:return fail(exc)
@router.post("/interview/questions/{question_id}/feedback")
def feedback(question_id:UUID,payload:FeedbackRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    ensure_user(db,user_id)
    try:return interview_service.feedback(db,user_id,question_id,payload.answer,payload.experience_id,payload.answer_id)
    except Exception as exc:return fail(exc)
# Compatibility alias for the previous user-answer endpoint.
@router.post("/interview/questions/{question_id}/analyse-answer")
def analyse(question_id:UUID,payload:FeedbackRequest,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
    return feedback(question_id,payload,db,user_id)
