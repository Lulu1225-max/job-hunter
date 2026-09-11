from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import experiences as api
from app.core import security
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.schemas.experiences import ExperienceCreate, ExperienceOrganization
from app.services import experience_service as module
from app.services.embedding_service import EmbeddingService, experience_source

SECRET="phase-six-test-secret-with-at-least-32-bytes"
ISSUER="https://unit-test.supabase.co/auth/v1"


def token(user_id):
    return jwt.encode({"sub":str(user_id),"email":"user@example.com","aud":"authenticated","iss":ISSUER,"role":"authenticated","exp":datetime.now(timezone.utc)+timedelta(minutes=10)},SECRET,algorithm="HS256")


class Db:
    def __init__(self): self.commits=0;self.flushes=0
    def commit(self): self.commits+=1
    def flush(self): self.flushes+=1


class FakeService:
    def __init__(self): self.rows={};self.calls=[]
    def list(self,db,user): self.calls.append("list");return [vars(r) for r in self.rows.values() if r.user_id==user]
    def create(self,db,user,payload):
        row=SimpleNamespace(id=uuid4(),user_id=user,**payload);self.rows[row.id]=row;return vars(row)
    def get(self,db,user,id):
        row=self.rows.get(id);return row if row and row.user_id==user else None
    def update(self,db,user,id,payload):
        row=self.get(db,user,id)
        if row:
            for k,v in payload.items(): setattr(row,k,v)
            return vars(row)
    def delete(self,db,user,id):
        if not self.get(db,user,id): return False
        del self.rows[id];return True


@pytest.fixture
def client(monkeypatch):
    service=FakeService();monkeypatch.setattr(api,"experience_service",service);monkeypatch.setattr(api,"ensure_user",lambda *args:None);monkeypatch.setattr(api,"serialize_model",vars)
    monkeypatch.setattr(settings,"supabase_url","https://unit-test.supabase.co");monkeypatch.setattr(settings,"supabase_publishable_key","test");monkeypatch.setattr(settings,"supabase_jwt_secret",SECRET);monkeypatch.setattr(settings,"supabase_jwt_audience","authenticated")
    monkeypatch.setattr(security,"_decode_with_jwks",lambda value:(_ for _ in()).throw(security.AuthError("test")));monkeypatch.setattr(security,"_verify_with_auth_server",lambda value:(_ for _ in()).throw(security.AuthError("test")))
    app.dependency_overrides[get_db]=lambda:Db()
    try: yield TestClient(app),service
    finally: app.dependency_overrides.clear()


def headers(user): return {"Authorization":f"Bearer {token(user)}"}


def test_authenticated_experience_crud_and_cross_user_ownership(client):
    http,service=client;a,b=uuid4(),uuid4()
    created=http.post("/api/v1/experiences",headers=headers(a),json={"title":"Launch","type":"project","description":"Built a launch plan","skills":[],"technologies":[]})
    assert created.status_code==200 and created.json()["user_id"]==str(a)
    id=created.json()["id"]
    assert len(http.get("/api/v1/experiences",headers=headers(a)).json())==1
    assert http.get(f"/api/v1/experiences/{id}",headers=headers(a)).status_code==200
    assert http.patch(f"/api/v1/experiences/{id}",headers=headers(a),json={"reflection":"Validate earlier"}).json()["reflection"]=="Validate earlier"
    assert http.get(f"/api/v1/experiences/{id}",headers=headers(b)).status_code==404
    assert http.delete(f"/api/v1/experiences/{id}",headers=headers(b)).status_code==404
    assert http.delete(f"/api/v1/experiences/{id}",headers=headers(a)).status_code==204 and service.rows=={}


def test_experience_validation_allows_partial_star_and_rejects_invalid_type():
    valid=ExperienceCreate(title="Story",type="leadership",action="Aligned the team")
    assert valid.description is None and valid.result is None
    with pytest.raises(ValueError): ExperienceCreate(title="Story",type="unknown",description="Notes")
    with pytest.raises(ValueError): ExperienceCreate(title="Story",type="other")


def test_list_page_path_does_not_call_openai(client,monkeypatch):
    http,service=client;monkeypatch.setattr(module.ai_client,"get_embedding",lambda *args:pytest.fail("page load embedded"));monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:pytest.fail("page load called AI"))
    assert http.get("/api/v1/experiences",headers=headers(uuid4())).status_code==200 and service.calls==["list"]


def exp(**values):
    base=dict(id=uuid4(),user_id=uuid4(),title="Stakeholder alignment",type="project",description="Resolved competing requirements",situation=None,task=None,action="Prioritized requirements",result="Team agreed",reflection=None,skills=["stakeholder management"],technologies=["Figma"],embedding=None,embedding_fingerprint=None)
    return SimpleNamespace(**{**base,**values})


def test_experience_embedding_create_reuse_change_and_failure(monkeypatch):
    row=exp();db=Db();calls=[];service=EmbeddingService();monkeypatch.setattr(module.ai_client,"get_embedding",lambda text:calls.append(text) or [1.0,0.0])
    first,first_hash=service.ensure_experience(db,row);second,second_hash=service.ensure_experience(db,row)
    assert first==second and first_hash==second_hash and len(calls)==1
    row.action="Negotiated a revised scope";service.ensure_experience(db,row)
    assert len(calls)==2 and row.embedding_fingerprint!=first_hash
    failing=exp();monkeypatch.setattr(module.embedding_service,"ensure_experience",lambda *args:(_ for _ in()).throw(RuntimeError("credits")))
    assert module.experience_service._best_effort_embedding(db,failing) is False and failing.embedding is None and failing.embedding_fingerprint is None


def test_service_create_persists_with_embedding_or_provider_failure(monkeypatch):
    db=Db();rows=[exp(),exp()]
    monkeypatch.setattr(module.experiences_repo,"create",lambda db,user,payload:rows.pop(0))
    monkeypatch.setattr(module,"serialize_model",lambda row:{"id":str(row.id)})
    def embedded(db,row): row.embedding=[1.0];row.embedding_fingerprint="digest";return row.embedding,"digest"
    monkeypatch.setattr(module.embedding_service,"ensure_experience",embedded)
    result=module.experience_service.create(db,uuid4(),{})
    assert result["id"] and db.commits==1
    monkeypatch.setattr(module.embedding_service,"ensure_experience",lambda *args:(_ for _ in()).throw(RuntimeError("credits")))
    result=module.experience_service.create(db,uuid4(),{})
    assert result["id"] and db.commits==2


@pytest.mark.parametrize("configured,expected",[("chinese","chinese"),("english","english"),("bilingual","bilingual"),(None,"chinese")])
def test_ai_organization_is_language_aware_preview_only_and_removes_invented_values(monkeypatch,configured,expected):
    created=[];payloads=[];profile={} if configured is None else {"ai_response_language":configured}
    monkeypatch.setattr(module.profile_repo,"get",lambda *args:profile);monkeypatch.setattr(module.experiences_repo,"create",lambda *args:created.append(args))
    def complete(**kwargs):
        payloads.append(kwargs["payload"]);return ExperienceOrganization.model_validate({"proposal":{"title":"项目","type":"project","description":"提升了 50%","result":"完成工作","technologies":["Python","InventedDB"]},"follow_up_questions":["结果是什么？"]})
    monkeypatch.setattr(module.ai_client,"structured_completion",complete)
    result=module.experience_service.organize(Db(),uuid4(),"我用 Python 完成工作，但没有记录指标。")
    assert result["response_language"]==expected and payloads[0]["response_language"]==expected
    assert result["proposal"]["description"] is None and result["proposal"]["technologies"]==["Python"]
    assert result["saved"] is False and created==[]


def test_retrieval_is_explicit_limited_and_never_auto_selects(monkeypatch):
    owner=uuid4();rows=[exp(user_id=owner,title=f"Story {i}") for i in range(6)];calls=[]
    monkeypatch.setattr(module.ai_client,"get_embedding",lambda text:calls.append(text) or [1.0,0.0])
    monkeypatch.setattr(module.profile_repo,"get",lambda *args:{"ai_response_language":"english"})
    monkeypatch.setattr(module.experiences_repo,"missing_embeddings",lambda db,user,limit:[])
    monkeypatch.setattr(module.experiences_repo,"vector_search",lambda db,user,vector,limit:[(row,.1+i*.1) for i,row in enumerate(rows[:limit])])
    result=module.experience_service.retrieve(Db(),owner,"stakeholder management",None,3)
    assert len(calls)==1 and len(result["recommendations"])==3
    assert result["selected_experience_id"] is None and all(item["selected"] is False for item in result["recommendations"])


def test_retrieval_handles_no_experiences_and_missing_embedding_failure(monkeypatch):
    missing=exp();monkeypatch.setattr(module.ai_client,"get_embedding",lambda text:[1.0]);monkeypatch.setattr(module.profile_repo,"get",lambda *args:{})
    monkeypatch.setattr(module.experiences_repo,"missing_embeddings",lambda *args:[missing]);monkeypatch.setattr(module.embedding_service,"ensure_experience",lambda *args:(_ for _ in()).throw(RuntimeError("unavailable")))
    monkeypatch.setattr(module.experiences_repo,"vector_search",lambda *args:[])
    result=module.experience_service.retrieve(Db(),missing.user_id,"question",None,3)
    assert result["recommendations"]==[] and result["embedded_missing_count"]==0


def test_pgvector_repository_query_filters_owner_orders_distance_and_limits():
    from app.repositories.database import ExperienceRepository
    class Capture:
        statement=None
        def execute(self,statement): self.statement=statement;return SimpleNamespace(all=lambda:[])
    db=Capture();owner=uuid4();ExperienceRepository().vector_search(db,owner,[0.0]*1536,5)
    sql=str(db.statement.compile(compile_kwargs={"literal_binds":True}))
    assert "experiences.user_id =" in sql and "<=>" in sql and "ORDER BY distance" in sql and "LIMIT 5" in sql
