from io import BytesIO
import pytest
from openpyxl import Workbook
from app.utils.excel import inspect_import, normalize_referral, parse_import

def xlsx(rows):
 wb=Workbook();ws=wb.active;ws.title="Jobs"
 for row in rows:ws.append(row)
 out=BytesIO();wb.save(out);return out.getvalue()

def test_excel_alias_mapping_preview_and_invalid_rows():
 content=xlsx([["Company Name","Job Title","City","Application Deadline","Notes"],["Acme","Engineer","Sydney","2027-01-02","x"],["","Analyst","","bad",""]])
 sheet=inspect_import(content,"jobs.xlsx")["sheets"][0]
 assert sheet["header_row"]==1 and sheet["mapping"]["Company Name"]=="company" and sheet["mapping"]["Job Title"]=="role"
 parsed=parse_import(content,"jobs.xlsx","Jobs",1,sheet["mapping"])
 assert len(parsed["jobs"])==1 and parsed["invalid"]==1 and parsed["issues"][0]["reason"]=="Missing company"

def test_csv_chinese_custom_mapping_ignore_and_bad_deadline_warning():
 content="企业,职位名称,自定义地点,备注,截止时间\n甲公司,数据分析师,上海,忽略我,不是日期\n".encode()
 sheet=inspect_import(content,"jobs.csv")["sheets"][0];mapping={**sheet["mapping"],"自定义地点":"location","备注":None}
 parsed=parse_import(content,"jobs.csv","CSV",1,mapping)
 assert parsed["jobs"][0]["location"]=="上海" and parsed["jobs"][0]["deadline"] is None and len(parsed["warnings"])==1 and parsed["invalid"]==0

def test_required_mappings_utf8_and_unsupported_formats():
 parsed=parse_import(b"Company,City\nA,Sydney\n","jobs.csv","CSV",1,{"Company":"company","City":"location"})
 assert parsed["jobs"][0]["company"]=="A" and parsed["jobs"][0]["role"] is None
 with pytest.raises(ValueError,match="Required mapping missing"):parse_import(b"Role,City\nEngineer,Sydney\n","jobs.csv","CSV",1,{"Role":"role","City":"location"})
 with pytest.raises(ValueError,match="UTF-8"):inspect_import(b"\xff\xfe","jobs.csv")
 with pytest.raises(ValueError,match="Only"):inspect_import(b"x","jobs.xls")

def test_duplicate_mapping_rejected():
 with pytest.raises(ValueError,match="only be mapped once"):parse_import(b"A,B\nx,y\n","jobs.csv","CSV",1,{"A":"company","B":"company"})

def test_missing_role_import_deduplication_is_deterministic():
 content=b"Company,Location,URL\nAcme,Sydney,https://example.com/jobs\n"
 mapping={"Company":"company","Location":"location","URL":"job_url"}
 first=parse_import(content,"jobs.csv","CSV",1,mapping)["jobs"][0]
 second=parse_import(content,"jobs.csv","CSV",1,mapping)["jobs"][0]
 assert first["role"] is None and first["source_hash"]==second["source_hash"]

def test_chinese_campus_metadata_aliases_and_normalization_for_excel_and_csv():
 headers=["公司名称","岗位名称","网申开始时间","校招分类","是否在内推","届次","企业性质"]
 values=["甲公司","工程师","2027-03-04","春招","是","2027届","国企"]
 for content,filename,sheet_name in ((xlsx([headers,values]),"jobs.xlsx","Jobs"),(",".join(headers).encode()+b"\n"+",".join(values).encode()+b"\n","jobs.csv","CSV")):
  sheet=inspect_import(content,filename)["sheets"][0]
  assert sheet["mapping"]==dict(zip(headers,["company","role","application_start_date","campus_category","referral_available","graduation_cohort","company_type"]))
  job=parse_import(content,filename,sheet_name,1,sheet["mapping"])["jobs"][0]
  assert job["application_start_date"]=="2027-03-04" and job["campus_category"]=="春招" and job["referral_available"] is True
  assert job["graduation_cohort"]=="2027届" and job["company_type"]=="国企"

@pytest.mark.parametrize(("raw","expected"),[("是",True),("否",False),("",None),("待确认",None)])
def test_referral_normalization(raw,expected):
 assert normalize_referral(raw) is expected

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
from app.services import job_service as service_module
from app.services.job_service import JobService

class FakeJobsRepo:
 def __init__(self): self.rows={};self.owners=[]
 def import_upsert(self,db,user_id,payload):
  self.owners.append(user_id);old=self.rows.get(payload["source_hash"])
  if old is None:self.rows[payload["source_hash"]]=payload;return "created"
  if old==payload:return "skipped"
  self.rows[payload["source_hash"]]={**old,**{k:v for k,v in payload.items() if v not in (None,"")}};return "updated"
class FakePreviewRepo:
 def __init__(self):self.rows={}
 def create(self,db,user_id,filename,content,preview_payload,expires_at):
  row=SimpleNamespace(id=uuid4(),user_id=user_id,filename=filename,file_content=content,preview_payload=preview_payload,expires_at=expires_at,status="preview",sheet_name="");self.rows[row.id]=row;return row
 def get(self,db,user_id,preview_id,lock=False):
  row=self.rows.get(preview_id);return row if row and row.user_id==user_id else None
 def save_options(self,db,row,options):row.preview_payload={**row.preview_payload,"selected_options":options}
 def confirm(self,db,row,sheet_name,counts):row.status="confirmed";row.sheet_name=sheet_name;row.file_content=None;return {"id":str(row.id),"status":row.status}
class FakeDb:
 def __init__(self):self.commits=0;self.rollbacks=0
 def commit(self):self.commits+=1
 def rollback(self):self.rollbacks+=1
def setup_repos(monkeypatch):
 jobs=FakeJobsRepo();previews=FakePreviewRepo();monkeypatch.setattr(service_module,"jobs_repo",jobs);monkeypatch.setattr(service_module,"job_import_previews_repo",previews);return jobs,previews
def options():return {"sheet_name":"CSV","header_row":1,"mapping":{"Company":"company","Role":"role"}}

def company_only_options():return {"sheet_name":"CSV","header_row":1,"mapping":{"Company":"company"}}

def test_preview_and_confirm_without_role_mapping(monkeypatch):
 jobs,_=setup_repos(monkeypatch);db=FakeDb();user=uuid4();svc=JobService();preview=svc.create_preview(db,user,"jobs.csv",b"Company\nAcme\n")
 assert svc.preview_rows(db,user,preview["preview_id"],company_only_options())["sample_rows"][0]["role"] is None
 assert svc.confirm_import(db,user,preview["preview_id"],company_only_options())["created"]==1
 assert next(iter(jobs.rows.values()))["role"] is None

def test_preview_survives_service_reconstruction_and_creates_zero_jobs(monkeypatch):
 jobs,_=setup_repos(monkeypatch);db=FakeDb();user=uuid4();created=JobService().create_preview(db,user,"jobs.csv",b"Company,Role\nAcme,Engineer\n")
 assert jobs.rows=={} and JobService().preview_rows(db,user,created["preview_id"],options())["total_rows"]==1 and jobs.rows=={}
 result=JobService().confirm_import(db,user,created["preview_id"],options());assert result["created"]==1 and jobs.owners==[user]
 assert db.commits==3 and db.rollbacks==0
def test_another_user_cannot_confirm_persisted_preview(monkeypatch):
 setup_repos(monkeypatch);db=FakeDb();owner=uuid4();preview=JobService().create_preview(db,owner,"jobs.csv",b"Company,Role\nA,B\n")
 with pytest.raises(KeyError):JobService().confirm_import(db,uuid4(),preview["preview_id"],options())
def test_expired_preview_is_rejected_and_marked_expired(monkeypatch):
 _,previews=setup_repos(monkeypatch);db=FakeDb();user=uuid4();preview=JobService().create_preview(db,user,"jobs.csv",b"Company,Role\nA,B\n");row=next(iter(previews.rows.values()));row.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
 with pytest.raises(KeyError):JobService().confirm_import(db,user,preview["preview_id"],options())
 assert row.status=="expired"
def test_confirmed_preview_cannot_be_confirmed_again(monkeypatch):
 jobs,_=setup_repos(monkeypatch);db=FakeDb();user=uuid4();svc=JobService();preview=svc.create_preview(db,user,"jobs.csv",b"Company,Role\nA,B\n");svc.confirm_import(db,user,preview["preview_id"],options())
 with pytest.raises(KeyError):JobService().confirm_import(db,user,preview["preview_id"],options())
 assert len(jobs.rows)==1

def test_confirmation_repository_uses_nonblocking_exclusive_row_lock():
 from sqlalchemy.dialects import postgresql
 from app.repositories.database import JobImportPreviewRepository
 class CaptureDb:
  def scalar(self,query):
   sql=str(query.compile(dialect=postgresql.dialect()))
   assert "FOR UPDATE NOWAIT" in sql
   return None
 JobImportPreviewRepository().get(CaptureDb(),uuid4(),uuid4(),lock=True)

def test_confirm_persists_all_campus_metadata(monkeypatch):
 jobs,_=setup_repos(monkeypatch);db=FakeDb();user=uuid4();content="Company,Role,开始时间,招聘分类,内推状态,毕业届次,公司性质\nAcme,Engineer,2027-01-02,秋招,否,2027届,民营\n".encode();svc=JobService();preview=svc.create_preview(db,user,"jobs.csv",content)
 mapping=preview["sheets"][0]["mapping"];svc.confirm_import(db,user,preview["preview_id"],{"sheet_name":"CSV","header_row":1,"mapping":mapping});row=next(iter(jobs.rows.values()))
 assert row["application_start_date"]=="2027-01-02" and row["campus_category"]=="秋招" and row["referral_available"] is False and row["graduation_cohort"]=="2027届" and row["company_type"]=="民营"
