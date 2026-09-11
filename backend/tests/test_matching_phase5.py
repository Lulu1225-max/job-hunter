from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services import matching as module
from app.services.embedding_service import EmbeddingService, fingerprint


class FakeDb:
    def __init__(self): self.commits=0; self.flushes=0
    def flush(self): self.flushes+=1
    def commit(self): self.commits+=1


def resume(user_id=None, text=None):
    return SimpleNamespace(id=uuid4(),user_id=user_id or uuid4(),extracted_text=text or "Built Python FastAPI services and PostgreSQL systems for product analytics. Led user research and cross-functional delivery.",detected_skills={"technical_skills":["Python","PostgreSQL"],"product_skills":["User research"],"soft_skills":[],"tools":[],"languages":[]},embedding=None,embedding_fingerprint=None)


def job(user_id=None, role="Product Engineer", description=None):
    return SimpleNamespace(id=uuid4(),user_id=user_id or uuid4(),company="Acme",role=role,description=description or "We need a Product Engineer to build Python FastAPI services, use PostgreSQL, analyze product data, collaborate with users, and deliver reliable software systems.",location="北京市",industry="Technology",job_type="Internship",campus_category="春招-实习",graduation_cohort="2027届",company_type="Private",required_skills=["Python","FastAPI","Kubernetes"],technical_skills=[],product_skills=[],soft_skills=[],education_requirements=[] ,embedding=None,embedding_fingerprint=None)


def profile():
    return {"target_roles":["Product Engineer"],"target_locations":["北京","上海"],"preferred_job_types":["Internship"],"graduation_year":2027,"technical_skills":["Python","PostgreSQL"],"product_skills":[],"soft_skills":[],"tools":[],"languages":[]}


def patch_resources(monkeypatch, owner, r, j, current=None):
    monkeypatch.setattr(module.jobs_repo,"get_row",lambda db,user_id,job_id: j if user_id==owner and job_id==j.id else None)
    monkeypatch.setattr(module.resumes_repo,"get",lambda db,user_id,resume_id: r if user_id==owner and resume_id==r.id else None)
    monkeypatch.setattr(module.resumes_repo,"default",lambda db,user_id: {"id":str(r.id)} if user_id==owner else None)
    monkeypatch.setattr(module.profile_repo,"get",lambda db,user_id: profile())
    monkeypatch.setattr(module.resume_analyses_repo,"current",lambda *args: current)
    monkeypatch.setattr(module.discovery_match_caches_repo,"current",lambda *args: None)
    monkeypatch.setattr(module.discovery_match_caches_repo,"create",lambda *args: None)


def test_embedding_generation_reuse_and_content_change(monkeypatch):
    calls=[]
    monkeypatch.setattr("app.services.embedding_service.ai_client.get_embedding",lambda text: calls.append(text) or [1.0,0.0])
    service=EmbeddingService(); db=FakeDb(); r=resume(text="Original extracted resume text")
    first,first_hash=service.ensure_resume(db,r)
    second,second_hash=service.ensure_resume(db,r)
    assert first==second==[1.0,0.0] and first_hash==second_hash and len(calls)==1
    r.extracted_text="Changed extracted resume text"
    _,changed_hash=service.ensure_resume(db,r)
    assert changed_hash != first_hash and len(calls)==2


def test_job_embedding_generation_and_reuse(monkeypatch):
    calls=[]; monkeypatch.setattr("app.services.embedding_service.ai_client.get_embedding",lambda text: calls.append(text) or [0.0,1.0])
    service=EmbeddingService(); j=job(); db=FakeDb()
    service.ensure_job(db,j); service.ensure_job(db,j)
    assert len(calls)==1 and "Description:" in calls[0]


def test_readiness_does_not_generate_embeddings(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner)
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda *args: pytest.fail("render generated embedding"))
    assert module.matching_service.readiness(j,profile(),True)["status"]=="ready"


def test_nullable_role_with_rich_jd_scores_deterministically(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner,role=None)
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    result=module.matching_service.discovery(FakeDb(),owner,j.id)
    assert result["status"]=="scored" and isinstance(result["overall_score"],int)
    assert result["components"]["role"] is None and result["semantic_score"]==100


def test_nullable_role_without_jd_is_limited_and_has_no_score(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner,role=None,description="Company campus recruitment information")
    patch_resources(monkeypatch,owner,r,j)
    result=module.matching_service.discovery(FakeDb(),owner,j.id)
    assert result["status"]=="limited_data" and result["overall_score"] is None and result["missing_jd"] is True


def test_semantic_only_preserves_semantic_score_without_overall_percentage(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner)
    j.description="Lead complex customer-focused initiatives, investigate service quality, coordinate stakeholders, document requirements, evaluate outcomes, and improve delivery across several business teams."
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.profile_repo,"get",lambda db,user_id:{})
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    result=module.matching_service.discovery(FakeDb(),owner,j.id)
    assert result["status"]=="semantic_only"
    assert result["overall_score"] is None
    assert result["semantic_score"]==100
    assert all(result["components"][name] is None for name in ("skills","role","education","location","job_type","cohort"))


def test_location_type_cohort_and_education_neutrality(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner)
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([0.0,1.0],"j"))
    result=module.matching_service.discovery(FakeDb(),owner,j.id)
    assert result["status"]=="scored" and isinstance(result["overall_score"],int)
    assert result["components"]["location"]==100 and result["components"]["job_type"]==100
    assert result["components"]["cohort"]==100 and result["components"]["education"] is None


def test_no_default_resume_returns_no_score(monkeypatch):
    owner=uuid4(); j=job(owner)
    monkeypatch.setattr(module.profile_repo,"get",lambda db,user_id:profile())
    monkeypatch.setattr(module.resumes_repo,"default",lambda db,user_id:None)
    result=module.matching_service.readiness(j,profile(),False)
    assert result["status"]=="no_resume" and result["overall_score"] is None


def test_deep_match_persists_deterministic_scores_and_llm_cannot_override(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner); db=FakeDb(); created=[]
    j.description += " Kubernetes experience is required for deployment."
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs: module.MatchNarrative(explanation="Grounded explanation",evidence=[{"skill":"Python","snippet":"Built Python FastAPI services"},{"skill":"Kubernetes","snippet":"Deployed a global Kubernetes platform"}],weak_areas=["Kubernetes"],rewrite_suggestions=[]))
    def create(db,user_id,payload):
        row=SimpleNamespace(id=uuid4(),user_id=user_id,**payload); created.append(row); return row
    monkeypatch.setattr(module.resume_analyses_repo,"create",create)
    result=module.matching_service.deep_match(db,owner,r.id,j.id)
    assert result["semantic_score"]==100 and result["keyword_score"]==75
    assert result["status"]=="scored" and result["overall_score"] is not None
    assert result["experience_relevance_score"] is not None
    assert result["missing_skills"]==["Kubernetes"]
    assert result["evidence"][0]["snippet"] in r.extracted_text and len(created)==1
    assert len(result["evidence"])==1
    assert "score" not in module.MatchNarrative.model_json_schema()["properties"]


def test_repeat_analysis_reuses_persisted_result(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner)
    saved=SimpleNamespace(id=uuid4(),resume_id=r.id,job_id=j.id,overall_score=88,keyword_score=80,semantic_score=90,experience_score=85,matched_keywords=[],missing_keywords=[],matched_skills=[],missing_skills=[],suggestions=[],evidence=[],weak_areas=[],explanation="saved",analysis_version=module.ANALYSIS_VERSION)
    patch_resources(monkeypatch,owner,r,j,current=saved)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda *args:pytest.fail("cached analysis regenerated embedding"))
    result=module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    assert result["cached"] is True and result["analysis_id"]==str(saved.id)


def _run_deep_match(monkeypatch, resume_text, description, required_skills=None):
    owner=uuid4(); r=resume(owner,text=resume_text); j=job(owner,description=description); db=FakeDb(); created=[]
    j.required_skills=required_skills or []
    j.technical_skills=[]; j.product_skills=[]; j.soft_skills=[]
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs: (_ for _ in ()).throw(RuntimeError()))
    def create(db,user_id,payload):
        row=SimpleNamespace(id=uuid4(),user_id=user_id,**payload); created.append(row); return row
    monkeypatch.setattr(module.resume_analyses_repo,"create",create)
    return module.matching_service.deep_match(db,owner,r.id,j.id),created


def test_deep_match_marks_unmeasurable_keyword_and_experience_components_unavailable(monkeypatch):
    result,created=_run_deep_match(
        monkeypatch,
        "Architected observability pipelines; mentored analysts; regional operations.",
        "Coordinate customer discovery initiatives, define service outcomes, manage stakeholder expectations, document business requirements, evaluate delivery quality, prioritize roadmap decisions, and communicate plans across multiple commercial teams.",
    )
    assert result["status"]=="semantic_only"
    assert result["keyword_score"] is None and result["experience_relevance_score"] is None
    assert result["matched_keywords"]==[] and result["missing_keywords"]==[]
    assert result["overall_score"] is None and result["semantic_score"]==100
    assert created[0].analysis_version=="phase5-v2"


def test_deep_match_keeps_true_zero_when_jd_has_measurable_keyword(monkeypatch):
    result,_=_run_deep_match(
        monkeypatch,
        "Architected observability pipelines; mentored analysts; regional operations.",
        "Build Kubernetes infrastructure for distributed production workloads, improve cluster reliability, automate deployment controls, investigate operational failures, coordinate incident response, and document platform standards for engineering teams.",
        ["Kubernetes"],
    )
    assert result["status"]=="scored"
    assert result["keyword_score"]==0 and result["experience_relevance_score"] is None
    assert result["matched_keywords"]==[] and result["missing_keywords"]==["Kubernetes"]
    assert result["overall_score"]==53


def test_deep_match_semantic_plus_experience_returns_composite_score(monkeypatch):
    result,_=_run_deep_match(
        monkeypatch,
        "Led orchestration; architected observability pipelines; mentored analysts; regional operations.",
        "Own customer discovery plus orchestration initiatives, define service outcomes, manage stakeholder expectations, document business requirements, evaluate delivery quality, prioritize roadmap decisions, communicate plans among multiple commercial teams.",
    )
    assert result["keyword_score"] is None
    assert result["experience_relevance_score"]==4
    assert result["status"]=="scored" and result["overall_score"]==63


def test_deep_match_phase5_v1_cache_is_not_reused(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner); requested=[]; created=[]
    old=SimpleNamespace(id=uuid4(),resume_id=r.id,job_id=j.id,overall_score=32,keyword_score=0,semantic_score=79,experience_score=0,matched_keywords=[],missing_keywords=[],matched_skills=[],missing_skills=[],suggestions=[],evidence=[],weak_areas=[],explanation="old",analysis_version="phase5-v1")
    patch_resources(monkeypatch,owner,r,j)
    def current(db,user_id,resume_id,job_id,resume_hash,job_hash,version,response_language):
        requested.append(version)
        return old if version=="phase5-v1" else None
    monkeypatch.setattr(module.resume_analyses_repo,"current",current)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs: (_ for _ in ()).throw(RuntimeError()))
    def create(db,user_id,payload):
        row=SimpleNamespace(id=uuid4(),user_id=user_id,**payload); created.append(row); return row
    monkeypatch.setattr(module.resume_analyses_repo,"create",create)
    result=module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    assert requested==["phase5-v2"] and result["cached"] is False
    assert len(created)==1 and created[0].analysis_version=="phase5-v2"


def test_changed_source_hash_is_used_for_staleness_lookup(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner); captured={}
    patch_resources(monkeypatch,owner,r,j)
    def current(db,user_id,resume_id,job_id,resume_hash,job_hash,version,response_language): captured.update(resume_hash=resume_hash,job_hash=job_hash); return None
    monkeypatch.setattr(module.resume_analyses_repo,"current",current)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r")); monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs: (_ for _ in ()).throw(RuntimeError()))
    monkeypatch.setattr(module.resume_analyses_repo,"create",lambda db,user_id,payload:SimpleNamespace(id=uuid4(),user_id=user_id,**payload))
    module.matching_service.deep_match(FakeDb(),owner,r.id,j.id); before=captured.copy(); r.extracted_text += " changed"
    module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    assert captured["resume_hash"] != before["resume_hash"]


def test_cross_user_resources_are_not_matchable(monkeypatch):
    owner,other=uuid4(),uuid4(); r=resume(owner); j=job(owner)
    patch_resources(monkeypatch,owner,r,j)
    with pytest.raises(KeyError): module.matching_service.deep_match(FakeDb(),other,r.id,j.id)


@pytest.mark.parametrize(
    ("configured","expected","explanation","weak_area","label","suggestion"),
    [
        ("chinese","chinese","中文说明","中文薄弱项","相关经历","中文建议"),
        ("english","english","English explanation","English weak area","Relevant experience","English suggestion"),
        ("bilingual","bilingual","中文说明 / English explanation","中文薄弱项 / English weak area","相关经历 / Relevant experience","中文建议 / English suggestion"),
        (None,"chinese","中文说明","中文薄弱项","相关经历","中文建议"),
    ],
)
def test_deep_match_uses_configured_response_language(monkeypatch,configured,expected,explanation,weak_area,label,suggestion):
    owner=uuid4(); r=resume(owner); j=job(owner); created=[]; payloads=[]
    patch_resources(monkeypatch,owner,r,j)
    configured_profile=profile()
    if configured is not None: configured_profile["ai_response_language"]=configured
    monkeypatch.setattr(module.profile_repo,"get",lambda db,user_id:configured_profile)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    def complete(**kwargs):
        payloads.append(kwargs["payload"])
        return module.MatchNarrative(explanation=explanation,evidence=[{"skill":label,"snippet":"Built Python FastAPI services"}],weak_areas=[weak_area],rewrite_suggestions=[{"type":label,"text":suggestion}])
    monkeypatch.setattr(module.ai_client,"structured_completion",complete)
    def create(db,user_id,payload):
        row=SimpleNamespace(id=uuid4(),user_id=user_id,**payload); created.append(row); return row
    monkeypatch.setattr(module.resume_analyses_repo,"create",create)
    result=module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    assert payloads[0]["response_language"]==expected
    assert result["explanation"]==explanation and result["weak_areas"]==[weak_area]
    assert result["evidence"][0]["skill"]==label
    assert result["suggested_resume_improvements"][0]["text"]==suggestion
    assert created[0].response_language==expected


def test_deep_match_language_change_does_not_reuse_other_language(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner); language={"value":"chinese"}; cache={}; calls=[]
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.profile_repo,"get",lambda db,user_id:{"ai_response_language":language["value"]})
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:([1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:([1.0,0.0],"j"))
    def current(db,user_id,resume_id,job_id,resume_hash,job_hash,version,response_language):
        return cache.get(response_language)
    def create(db,user_id,payload):
        row=SimpleNamespace(id=uuid4(),user_id=user_id,**payload); cache[payload["response_language"]]=row; return row
    def complete(**kwargs):
        selected=kwargs["payload"]["response_language"]; calls.append(selected)
        return module.MatchNarrative(explanation=selected,evidence=[],weak_areas=[],rewrite_suggestions=[])
    monkeypatch.setattr(module.resume_analyses_repo,"current",current)
    monkeypatch.setattr(module.resume_analyses_repo,"create",create)
    monkeypatch.setattr(module.ai_client,"structured_completion",complete)
    chinese=module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    language["value"]="english"
    english=module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    language["value"]="chinese"
    chinese_cached=module.matching_service.deep_match(FakeDb(),owner,r.id,j.id)
    assert chinese["explanation"]=="chinese" and english["explanation"]=="english"
    assert chinese_cached["cached"] is True and calls==["chinese","english"]


def test_discovery_match_cache_reuses_and_invalidates_by_sources_and_version(monkeypatch):
    owner=uuid4(); r=resume(owner); j=job(owner); db=FakeDb(); cache={}; embedding_calls=[]
    patch_resources(monkeypatch,owner,r,j)
    def key(user_id,resume_id,job_id,resume_hash,job_hash,version): return (user_id,resume_id,job_id,resume_hash,job_hash,version)
    def current(db,user_id,resume_id,job_id,resume_hash,job_hash,version): return cache.get(key(user_id,resume_id,job_id,resume_hash,job_hash,version))
    def create(db,user_id,resume_id,job_id,resume_hash,job_hash,version,result):
        cache[key(user_id,resume_id,job_id,resume_hash,job_hash,version)]=SimpleNamespace(result_payload=dict(result))
    monkeypatch.setattr(module.discovery_match_caches_repo,"current",current)
    monkeypatch.setattr(module.discovery_match_caches_repo,"create",create)
    monkeypatch.setattr(module.embedding_service,"ensure_resume",lambda db,row:(embedding_calls.append(("resume",row.extracted_text)) or [1.0,0.0],"r"))
    monkeypatch.setattr(module.embedding_service,"ensure_job",lambda db,row:(embedding_calls.append(("job",row.description)) or [1.0,0.0],"j"))
    monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:pytest.fail("Discovery Match called an LLM"))

    first=module.matching_service.discovery(db,owner,j.id)
    second=module.matching_service.discovery(db,owner,j.id)
    assert first["cached"] is False and second["cached"] is True
    assert len(cache)==1 and len(embedding_calls)==2

    r.extracted_text += " changed"
    assert module.matching_service.discovery(db,owner,j.id)["cached"] is False
    j.description += " changed job content"
    assert module.matching_service.discovery(db,owner,j.id)["cached"] is False
    monkeypatch.setattr(module,"DISCOVERY_MATCH_VERSION","phase5-discovery-v2")
    assert module.matching_service.discovery(db,owner,j.id)["cached"] is False
    assert len(cache)==4 and len(embedding_calls)==8


def test_other_user_cannot_reach_discovery_cache(monkeypatch):
    owner,other=uuid4(),uuid4(); r=resume(owner); j=job(owner)
    patch_resources(monkeypatch,owner,r,j)
    monkeypatch.setattr(module.discovery_match_caches_repo,"current",lambda *args:pytest.fail("cross-user request reached cache"))
    with pytest.raises(KeyError): module.matching_service.discovery(FakeDb(),other,j.id)
