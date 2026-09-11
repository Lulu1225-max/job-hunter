from __future__ import annotations
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from app.scripts import reset_demo as module
from app.scripts.seed_demo_applications import APPLICATIONS, EXPERIENCES, JOBS
class FakeDb:
 def __init__(self,paths=()):self.paths=list(paths);self.statements=[];self.commits=0
 def scalars(self,statement):return SimpleNamespace(all=lambda:self.paths)
 def execute(self,statement):self.statements.append(statement)
 def flush(self):pass
 def commit(self):self.commits+=1
class FakeStorage:
 def __init__(self):self.deleted=[]
 def delete(self,path):self.deleted.append(path)
def test_clear_targets_only_demo_user_and_storage_prefix():
 demo,normal=uuid4(),uuid4();db=FakeDb([f"{demo}/resume/file.pdf",f"{normal}/resume/private.pdf","/demo/canonical.pdf"]);paths=module.clear_demo_data(db,demo)
 assert paths==[f"{demo}/resume/file.pdf"] and len(db.statements)==10
 for statement in db.statements:
  params=statement.compile().params;assert demo in params.values() and normal not in params.values()
def test_reset_restores_canonical_state_and_is_idempotent(monkeypatch):
 demo=uuid4();db=FakeDb();storage=FakeStorage();state={"jobs":["changed"],"applications":["changed"],"experiences":["changed"]}
 monkeypatch.setattr(module,"ensure_user",lambda *args,**kwargs:None)
 def clear(_db,user_id):
  assert user_id==demo
  for values in state.values():values.clear()
  return [f"{demo}/resume/upload.pdf"]
 def seed(_db,user_id,email):
  assert user_id==demo and email=="demo@example.com"
  state["jobs"].extend((j["company"],j["role"]) for j in JOBS);state["applications"].extend((a["company"],a["role"]) for a in APPLICATIONS);state["experiences"].extend(e["title"] for e in EXPERIENCES)
 monkeypatch.setattr(module,"clear_demo_data",clear);monkeypatch.setattr(module,"seed_demo_state",seed)
 module.reset_demo(db,demo,"demo@example.com",storage=storage);first={k:list(v) for k,v in state.items()};module.reset_demo(db,demo,"demo@example.com",storage=storage)
 assert state==first and len(state["jobs"])==len(JOBS) and len(state["applications"])==len(APPLICATIONS) and len(state["experiences"])==len(EXPERIENCES)
 assert db.commits==2 and storage.deleted==[f"{demo}/resume/upload.pdf"]*2
def test_shared_demo_warning_translations_exist():
 root=Path(__file__).resolve().parents[2]/"frontend"/"messages";en=json.loads((root/"en.json").read_text())["auth"]["demoWarning"];zh=json.loads((root/"zh.json").read_text())["auth"]["demoWarning"]
 assert "shared environment" in en and "Do not upload sensitive" in en and "共享环境" in zh and "请勿上传敏感个人信息" in zh

def test_missing_job_role_fallback_translations_exist():
 root=Path(__file__).resolve().parents[2]/"frontend"/"messages"
 assert json.loads((root/"en.json").read_text())["jobs"]["roleMissing"]=="Role not provided"
 assert json.loads((root/"zh.json").read_text())["jobs"]["roleMissing"]=="职位待补充"
