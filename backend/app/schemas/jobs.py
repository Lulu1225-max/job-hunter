from __future__ import annotations
from pydantic import BaseModel, Field, field_validator

class JobBase(BaseModel):
 company:str=Field(min_length=1,max_length=255); role:str|None=Field(None,min_length=1,max_length=255); location:str|None=Field(None,max_length=255); job_url:str|None=Field(None,max_length=2000); salary:str|None=Field(None,max_length=255); description:str|None=None; industry:str|None=Field(None,max_length=255); job_type:str|None=Field(None,max_length=100); deadline:str|None=None; application_start_date:str|None=None; campus_category:str|None=Field(None,max_length=120); referral_available:bool|None=None; graduation_cohort:str|None=Field(None,max_length=120); company_type:str|None=Field(None,max_length=120)
 @field_validator("company")
 @classmethod
 def required_text(cls,v:str)->str:
  v=v.strip()
  if not v:raise ValueError("must not be blank")
  return v
 @field_validator("job_url")
 @classmethod
 def valid_url(cls,v):
  if v and not (v.startswith("http://") or v.startswith("https://")):raise ValueError("job_url must use http or https")
  return v
class JobCreate(JobBase):pass
class JobUpdate(BaseModel):
 company:str|None=Field(None,min_length=1,max_length=255); role:str|None=Field(None,min_length=1,max_length=255); location:str|None=Field(None,max_length=255); job_url:str|None=Field(None,max_length=2000); salary:str|None=Field(None,max_length=255); description:str|None=None; industry:str|None=Field(None,max_length=255); job_type:str|None=Field(None,max_length=100); deadline:str|None=None; application_start_date:str|None=None; campus_category:str|None=Field(None,max_length=120); referral_available:bool|None=None; graduation_cohort:str|None=Field(None,max_length=120); company_type:str|None=Field(None,max_length=120)
class ImportOptions(BaseModel):
 sheet_name:str; header_row:int=Field(ge=1,le=10000); mapping:dict[str,str|None]
class ImportCounts(BaseModel):
 total_rows:int; created:int; updated:int; skipped:int; invalid:int
