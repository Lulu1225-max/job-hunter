from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.schemas.interviews import AnswerOutput,FeedbackOutput,InterviewCreate,ParsedQuestions,QuestionList
from app.services import interview_service as module

class Db:
 def __init__(self):self.commits=0
 def commit(self):self.commits+=1

def obj(**kw):return SimpleNamespace(**kw)
def exp(owner=None):return obj(id=uuid4(),user_id=owner or uuid4(),title="BIM product",type="internship",description="Managed requirements",situation="Teams disagreed",task="Align scope",action="Prioritized requests with Figma",result="Team agreed",reflection="Clarify decisions",skills=["stakeholder management"],technologies=["Figma"],embedding=None,embedding_fingerprint=None)

def setup(monkeypatch,category="behavioral",question_text="Tell me about a time you resolved conflict"):
 owner=uuid4();application=obj(id=uuid4(),user_id=owner,job_id=None,company="Acme",role="Product Manager",status="applied");question=obj(id=uuid4(),user_id=owner,application_id=application.id,interview_id=None,company="Acme",role="Product Manager",question=question_text,category=category,source="user_added",ai_feedback=None,user_answer=None);experience=exp(owner)
 monkeypatch.setattr(module.applications_repo,"get",lambda db,user,id:application if user==owner and id==application.id else None)
 monkeypatch.setattr(module.interview_questions_repo,"get",lambda db,user,id:question if user==owner and id==question.id else None)
 monkeypatch.setattr(module.experiences_repo,"get",lambda db,user,id:experience if user==owner and id==experience.id else None)
 monkeypatch.setattr(module.profile_repo,"get",lambda db,user:{"ai_response_language":"chinese"})
 monkeypatch.setattr(module,"serialize_model",lambda row:{k:(str(v) if hasattr(v,"hex") else v) for k,v in vars(row).items() if not k.startswith("_")})
 return owner,application,question,experience

def test_prep_allows_any_application_status_and_has_no_auto_selection(monkeypatch):
 owner,app,q,e=setup(monkeypatch);monkeypatch.setattr(module.interviews_repo,"list",lambda *args:[]);monkeypatch.setattr(module.interview_questions_repo,"list_for_application",lambda *args:[])
 result=module.interview_service.prep(Db(),owner,app.id)
 assert result["application"]["status"]=="applied" and result["recommended_experiences"]==[] and result["selected_experience_id"] is None

def test_question_parse_is_grounded_preview_and_does_not_save(monkeypatch):
 owner,*_=setup(monkeypatch);saved=[];monkeypatch.setattr(module.interview_questions_repo,"create",lambda *args:saved.append(args))
 monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:ParsedQuestions.model_validate({"questions":[{"question":"How did you prioritize requirements?","category":"product","source_excerpt":"prioritize requirements"},{"question":"Why Google?","category":"motivation","source_excerpt":"prioritize requirements"}]}))
 result=module.interview_service.parse(Db(),owner,"They asked me to prioritize requirements during a conflict.")
 assert len(result["questions"])==1 and result["saved"] is False and saved==[]

def test_question_generation_is_explicit_grounded_and_language_aware(monkeypatch):
 owner,app,*_=setup(monkeypatch);payloads=[];saved=[]
 monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:(payloads.append(kwargs["payload"]) or QuestionList.model_validate({"questions":[{"question":"How would you prioritize this roadmap?","category":"product","source":"ai_generated"}]})))
 monkeypatch.setattr(module.interview_service,"add_question",lambda db,user,payload:saved.append(payload) or payload)
 result=module.interview_service.generate_questions(Db(),owner,app.id,"product",5)
 assert result["questions"][0]["source"]=="ai_generated" and payloads[0]["response_language"]=="chinese" and payloads[0]["application"]["company"]=="Acme"

def test_retrieval_reuses_phase6_and_keeps_candidates_unselected(monkeypatch):
 owner,app,q,e=setup(monkeypatch);captured=[]
 monkeypatch.setattr(module.experience_service,"retrieve",lambda db,user,query,context,limit:captured.append((user,query,context,limit)) or {"recommendations":[{"experience_id":str(e.id),"selected":False}],"selected_experience_id":None})
 result=module.interview_service.retrieve(Db(),owner,q.id,3)
 assert captured[0][1]==q.question and result["recommendations"][0]["selected"] is False and result["selected_experience_id"] is None

def test_experience_answer_requires_explicit_owned_selection(monkeypatch):
 owner,app,q,e=setup(monkeypatch)
 with pytest.raises(ValueError):module.interview_service.generate_answer(Db(),owner,q.id,None,"1min")
 with pytest.raises(KeyError):module.interview_service.generate_answer(Db(),owner,q.id,uuid4(),"1min")

def test_technical_concept_answer_does_not_require_experience(monkeypatch):
 owner,app,q,e=setup(monkeypatch,"database","What is a database index?");created=[]
 monkeypatch.setattr(module.interview_answers_repo,"current",lambda *args:None);monkeypatch.setattr(module.interview_answers_repo,"create",lambda db,payload:(created.append(payload) or obj(id=uuid4(),created_at=None,updated_at=None,feedback=None,**payload)))
 monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:AnswerOutput(answer_1min="数据库索引是一种查询数据结构。"))
 result=module.interview_service.generate_answer(Db(),owner,q.id,None,"1min")
 assert result["answer_1min"] and created[0]["experience_id"] is None

def test_answer_is_grounded_language_aware_and_cached_by_all_sources(monkeypatch):
 owner,app,q,e=setup(monkeypatch);cache={};calls=[]
 def current(db,user,qid,eid,qh,eh,jh,lang,version):return cache.get((user,qid,eid,qh,eh,jh,lang,version))
 def create(db,payload):
  row=obj(id=uuid4(),created_at=None,updated_at=None,feedback=None,**payload);cache[(payload["user_id"],payload["question_id"],payload["experience_id"],payload["question_fingerprint"],payload["experience_fingerprint"],payload["job_fingerprint"],payload["response_language"],payload["answer_version"])]=row;return row
 monkeypatch.setattr(module.interview_answers_repo,"current",current);monkeypatch.setattr(module.interview_answers_repo,"create",create)
 def complete(**kwargs):calls.append(kwargs["payload"]);return AnswerOutput(answer_1min="我使用 Figma 协调需求，提升了 25%。随后使用 Kubernetes。")
 monkeypatch.setattr(module.ai_client,"structured_completion",complete)
 first=module.interview_service.generate_answer(Db(),owner,q.id,e.id,"1min");second=module.interview_service.generate_answer(Db(),owner,q.id,e.id,"1min")
 assert "25" not in (first["answer_1min"] or "") and "Kubernetes" not in (first["answer_1min"] or "")
 assert calls[0]["response_language"]=="chinese" and calls[0]["selected_experience"]["id"]==str(e.id) and second["cached"] is True and len(calls)==1
 e.action="Changed source";module.interview_service.generate_answer(Db(),owner,q.id,e.id,"1min")
 assert len(calls)==2

def test_answer_language_and_length_do_not_cross_cache(monkeypatch):
 owner,app,q,e=setup(monkeypatch);keys=[]
 monkeypatch.setattr(module.interview_answers_repo,"current",lambda *args:(keys.append(args[-2:]) or None));monkeypatch.setattr(module.interview_answers_repo,"create",lambda db,payload:obj(id=uuid4(),created_at=None,updated_at=None,feedback=None,**payload));monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:AnswerOutput(answer_30s="回答",answer_1min="回答"))
 module.interview_service.generate_answer(Db(),owner,q.id,e.id,"30s");module.interview_service.generate_answer(Db(),owner,q.id,e.id,"1min")
 assert keys[0][1]!=keys[1][1]
 monkeypatch.setattr(module.profile_repo,"get",lambda *args:{"ai_response_language":"english"});module.interview_service.generate_answer(Db(),owner,q.id,e.id,"1min")
 assert keys[-1][0]=="english"

def test_feedback_supports_user_answer_grounding_followups_and_cache(monkeypatch):
 owner,app,q,e=setup(monkeypatch);calls=[]
 output=FeedbackOutput(strengths=["具体"],weaknesses=["结果不足"],missing_evidence=["指标"],structure="清楚",star_completeness="结果较弱",clarity="清楚",specificity="可加强",relevance="相关",follow_up_questions=["为什么？","取舍是什么？","会如何改进？"],improved_answer="我协调需求并提升 50%。")
 monkeypatch.setattr(module.ai_client,"structured_completion",lambda **kwargs:(calls.append(1) or output))
 first=module.interview_service.feedback(Db(),owner,q.id,"我协调了需求。",e.id,None);second=module.interview_service.feedback(Db(),owner,q.id,"我协调了需求。",e.id,None)
 assert first["strengths"] and len(first["follow_up_questions"])==3 and "50" not in first["improved_answer"] and second["cached"] is True and len(calls)==1

def test_actual_interview_creates_owned_actual_questions_and_review_fields(monkeypatch):
 owner,app,q,e=setup(monkeypatch);created=[];questions=[]
 monkeypatch.setattr(module.interviews_repo,"create",lambda db,user,application_id,payload:(created.append((user,payload)) or obj(id=uuid4(),user_id=user,application_id=application_id,created_at=None,updated_at=None,**payload)))
 monkeypatch.setattr(module.interview_questions_repo,"create",lambda db,user,payload:questions.append((user,payload)) or payload)
 result=module.interview_service.create_interview(Db(),owner,{"application_id":app.id,"round":"hr_round","interview_type":"behavioral","status":"completed","outcome":"passed","difficulty":4,"confidence":3,"went_well":"Clear examples","to_improve":"Be concise","actual_questions":["Why us?"]})
 assert result["outcome"]=="passed" and result["application"]["company"]=="Acme" and result["application"]["role"]=="Product Manager"
 assert created[0][0]==owner and questions[0][0]==owner and questions[0][1]["source"]=="actual_interview" and result["actual_questions"]

def test_actual_interview_rejects_cross_user_application(monkeypatch):
 owner,app,*_=setup(monkeypatch);other=uuid4()
 with pytest.raises(KeyError):module.interview_service.create_interview(Db(),other,{"application_id":app.id,"actual_questions":[]})

def test_interview_schema_validates_outcome_and_ranges():
 with pytest.raises(ValueError):InterviewCreate(application_id=uuid4(),outcome="hired")
 with pytest.raises(ValueError):InterviewCreate(application_id=uuid4(),difficulty=6)
