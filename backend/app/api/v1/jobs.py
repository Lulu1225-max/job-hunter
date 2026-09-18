from __future__ import annotations
from uuid import UUID
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
import math
from time import perf_counter
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from app.core.database import get_db
from app.core.security import get_current_user_id
from app.repositories.database import ensure_user, profile_repo, resumes_repo
from app.schemas.jobs import ImportOptions, JobCreate, JobUpdate
from app.services.job_service import job_service
from app.services.matching import matching_service
from app.services.analytics import elapsed_ms, track_event
router=APIRouter()
def not_found():return HTTPException(404,detail={"error":{"code":"JOB_NOT_FOUND","message":"Job not found"}})
def bad(exc):return HTTPException(422,detail={"error":{"code":"INVALID_JOB_IMPORT","message":str(exc)}})
@router.post("/import/preview")
async def create_import_preview(file:UploadFile=File(...),db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 try:return job_service.create_preview(db,user_id,file.filename or "upload",await file.read())
 except ValueError as exc:raise bad(exc)
@router.post("/import/preview/{preview_id}")
def preview_rows(preview_id:str,payload:ImportOptions,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 try:return job_service.preview_rows(db,user_id,preview_id,payload.model_dump())
 except KeyError as exc:raise HTTPException(404,detail={"error":{"code":"IMPORT_NOT_FOUND","message":str(exc)}})
 except ValueError as exc:raise bad(exc)
@router.post("/import/confirm/{preview_id}")
def confirm(preview_id:str,payload:ImportOptions,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 try:return job_service.confirm_import(db,user_id,preview_id,payload.model_dump())
 except KeyError as exc:raise HTTPException(404,detail={"error":{"code":"IMPORT_NOT_FOUND","message":str(exc)}})
 except ValueError as exc:raise bad(exc)
 except OperationalError as exc:
  if getattr(exc.orig,"sqlstate",None)=="55P03":
   raise HTTPException(409,detail={"error":{"code":"IMPORT_CONFIRM_IN_PROGRESS","message":"This import preview is already being confirmed"}}) from exc
  raise
@router.get("")
def list_jobs_endpoint(q:str|None=None,keyword:str|None=None,company:str|None=None,role:str|None=None,location:str|None=None,industry:str|None=None,job_type:str|None=None,sort:str|None="newest",page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 rows,total=job_service.page_jobs(db,user_id,locals(),page,page_size)
 profile=profile_repo.get(db,user_id)
 default_resume=resumes_repo.default(db,user_id)
 for item in rows:
  item["match"]=matching_service.readiness(item,profile,bool(default_resume))
 return {"items":rows,"page":page,"page_size":page_size,"total":total,"total_pages":math.ceil(total/page_size) if total else 0}
@router.post("")
def create_job(payload:JobCreate,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id); return job_service.create_job(db,user_id,payload.model_dump())
@router.get("/{job_id}")
def get_job(job_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id); result=job_service.get_job(db,user_id,job_id)
 if not result:raise not_found()
 return result
@router.patch("/{job_id}")
def update_job(job_id:UUID,payload:JobUpdate,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id); result=job_service.update_job(db,user_id,job_id,payload.model_dump(exclude_unset=True))
 if not result:raise not_found()
 return result
@router.delete("/{job_id}",status_code=204)
def delete_job(job_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 if not job_service.delete_job(db,user_id,job_id):raise not_found()

@router.post("/{job_id}/discovery-match")
def discovery_match(job_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 try:return matching_service.discovery(db,user_id,job_id)
 except KeyError:raise not_found()
 except (RuntimeError,ValueError) as exc:raise HTTPException(502,detail={"error":{"code":"MATCH_UNAVAILABLE","message":str(exc)}})

@router.post("/{job_id}/match")
def match_job(job_id:UUID,resume_id:UUID,db:Session=Depends(get_db),user_id:UUID=Depends(get_current_user_id)):
 ensure_user(db,user_id)
 started=perf_counter()
 track_event(user_id=user_id,event_name="resume_match_started",job_id=job_id,resume_id=resume_id,status="success",metadata={"match_mode":"deep"})
 try:
  result=matching_service.deep_match(db,user_id,resume_id,job_id)
 except (KeyError,ValueError,RuntimeError,TimeoutError) as exc:
  error_type=("resume_missing" if isinstance(exc,KeyError) and "Resume" in str(exc) else
              "insufficient_job_description" if "meaningful description" in str(exc) else
              "resume_missing" if "extracted text" in str(exc) else
              "timeout" if isinstance(exc,TimeoutError) else
              "ai_request_failed" if isinstance(exc,RuntimeError) else "unknown")
  track_event(user_id=user_id,event_name="resume_match_failed",job_id=None if isinstance(exc,KeyError) and "Job" in str(exc) else job_id,resume_id=None if isinstance(exc,KeyError) and "Resume" in str(exc) else resume_id,status="failed",error_type=error_type,latency_ms=elapsed_ms(started))
  if isinstance(exc,KeyError):raise HTTPException(404,detail={"error":{"code":"MATCH_RESOURCE_NOT_FOUND","message":"Resume or job not found"}})
  if isinstance(exc,ValueError):raise HTTPException(422,detail={"error":{"code":"MATCH_DATA_INSUFFICIENT","message":str(exc)}})
  raise HTTPException(502,detail={"error":{"code":"MATCH_UNAVAILABLE","message":str(exc)}})
 except Exception:
  track_event(user_id=user_id,event_name="resume_match_failed",job_id=job_id,resume_id=resume_id,status="failed",error_type="unknown",latency_ms=elapsed_ms(started))
  raise
 track_event(user_id=user_id,event_name="resume_match_completed",job_id=job_id,resume_id=resume_id,status="success",latency_ms=elapsed_ms(started),metadata={"cache_hit":result.get("cached",False)})
 return result
