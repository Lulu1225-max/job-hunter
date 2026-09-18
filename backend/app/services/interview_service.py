from __future__ import annotations
import re
from time import perf_counter
from typing import Any
from uuid import UUID
from sqlalchemy.orm import Session

from app.repositories.database import applications_repo,experiences_repo,interview_answers_repo,interview_questions_repo,interviews_repo,jobs_repo,profile_repo,serialize_model
from app.schemas.interviews import AnswerOutput,FeedbackOutput,ParsedQuestions,QuestionList
from app.services.ai.client import ai_client
from app.services.embedding_service import experience_source,fingerprint,job_source
from app.services.experience_service import experience_service
from app.services.matching import response_language,tokens
from app.services.analytics import elapsed_ms, track_event

ANSWER_VERSION="phase7-answer-v1"
FEEDBACK_VERSION="phase7-feedback-v1"
TECHNICAL_CATEGORIES={"programming","data structures & algorithms","backend","database","networking","system design basics","debugging","technical"}
PERSONAL_CUES=("tell me about a time","describe a time","your experience","你曾经","讲一次","经历")

def _hash(value:Any)->str:return fingerprint(str(value or ""))
def _strip_unsupported_numbers(text:str|None,sources:str)->str|None:
    if not text:return text
    allowed=set(re.findall(r"\d+(?:[.,]\d+)?%?",sources))
    parts=re.split(r"(?<=[。！？.!?])",text)
    kept=[part for part in parts if set(re.findall(r"\d+(?:[.,]\d+)?%?",part)).issubset(allowed)]
    return "".join(kept).strip()
def _strip_unsupported_technologies(text:str|None,sources:str)->str|None:
    if not text:return text
    common={"the","this","that","when","while","then","after","before","because","i","we","my","our","first","finally","for","if","in","to"}
    parts=re.split(r"(?<=[。！？.!?])",text);kept=[];source=sources.casefold()
    for part in parts:
        terms=[x for x in re.findall(r"\b[A-Z][A-Za-z0-9.+#-]{2,}\b",part) if x.casefold() not in common]
        if all(term.casefold() in source for term in terms):kept.append(part)
    return "".join(kept).strip()

class InterviewService:
    def list(self,db,user):return interviews_repo.list(db,user)
    def get_interview(self,db,user,id):
        row=interviews_repo.get(db,user,id)
        if not row:raise KeyError("Interview not found")
        app=applications_repo.get(db,user,row.application_id)
        questions=[q for q in interview_questions_repo.list_for_application(db,user,row.application_id) if q.get("interview_id")==str(row.id) and q.get("source")=="actual_interview"]
        return {**serialize_model(row),"application":serialize_model(app),"actual_questions":questions}
    def prep(self,db,user,application_id):
        app=applications_repo.get(db,user,application_id)
        if not app:raise KeyError("Application not found")
        return {"application":serialize_model(app),"interviews":[x for x in interviews_repo.list(db,user) if x["application_id"]==str(application_id)],"questions":interview_questions_repo.list_for_application(db,user,application_id),"recommended_experiences":[],"selected_experience_id":None}
    def create_interview(self,db,user,payload):
        app=applications_repo.get(db,user,payload["application_id"])
        if not app:raise KeyError("Application not found")
        questions=payload.pop("actual_questions",[]);application_id=payload.pop("application_id")
        row=interviews_repo.create(db,user,application_id,payload)
        saved_questions=[]
        for text in questions:
            if text.strip():saved_questions.append(interview_questions_repo.create(db,user,{"interview_id":row.id,"application_id":application_id,"company":app.company,"role":app.role,"question":text.strip(),"category":"actual interview","source":"actual_interview"}))
        db.commit()
        return {**serialize_model(row),"application":serialize_model(app),"actual_questions":saved_questions}
    def update_interview(self,db,user,id,payload):
        row=interviews_repo.update(db,user,id,payload)
        if row:db.commit();return serialize_model(row)
    def delete_interview(self,db,user,id):
        deleted=interviews_repo.delete(db,user,id)
        if deleted:db.commit()
        return deleted
    def add_question(self,db,user,payload):
        self._validate_links(db,user,payload)
        row=interview_questions_repo.create(db,user,{**payload,"source":payload.get("source") or "user_added"});db.commit();return row
    def questions(self,db,user,category=None,source=None,application_id=None):return interview_questions_repo.list(db,user,category,source,application_id)
    def parse(self,db,user,text):
        language=response_language(profile_repo.get(db,user));parsed=ai_client.structured_completion(prompt_name="interview_question_parser",schema=ParsedQuestions,payload={"response_language":language,"pasted_text":text})
        valid=[]
        for item in parsed.questions:
            supported=bool(tokens(item.question)&tokens(item.source_excerpt)) or item.source_excerpt.casefold() in item.question.casefold()
            if item.source_excerpt.strip() and item.source_excerpt.casefold() in text.casefold() and supported:valid.append({"question":item.question,"category":item.category,"source":"public_research"})
        return {"questions":valid,"requires_confirmation":True,"saved":False}
    def confirm_questions(self,db,user,questions):
        saved=[self.add_question(db,user,item) for item in questions];return {"questions":saved,"saved":True}
    def generate_questions(self,db,user,application_id,category,count):
        app=applications_repo.get(db,user,application_id)
        if not app:raise KeyError("Application not found")
        job=jobs_repo.get_row(db,user,app.job_id) if app.job_id else None;language=response_language(profile_repo.get(db,user));context=job_source(job) if job else f"{app.company}\n{app.role or ''}"
        output=ai_client.structured_completion(prompt_name="interview_question_generator",schema=QuestionList,payload={"response_language":language,"application":{"company":app.company,"role":app.role},"job_context":context,"category":category,"count":count})
        saved=[]
        for item in output.questions[:count]:saved.append(self.add_question(db,user,{**item.model_dump(),"application_id":application_id,"company":app.company,"role":app.role,"source":"ai_generated"}))
        return {"questions":saved}
    def retrieve(self,db,user,question_id,limit):
        question=self._question(db,user,question_id);context=self._context(db,user,question)
        app=applications_repo.get(db,user,question.application_id) if question.application_id else None
        if app and app.job_id:
            return experience_service.retrieve(db,user,question.question,context["text"],limit,app.job_id)
        return experience_service.retrieve(db,user,question.question,context["text"],limit)
    def generate_answer(self,db,user,question_id,experience_id,length,regenerate=False):
        started=perf_counter()
        question=self._question(db,user,question_id);technical=self._technical(question)
        experience=experiences_repo.get(db,user,experience_id) if experience_id else None
        if experience_id and not experience:raise KeyError("Experience not found")
        if not technical and not experience:raise ValueError("Select an Experience before generating this answer")
        app=applications_repo.get(db,user,question.application_id) if question.application_id else None
        job_id=app.job_id if app else None
        if experience:
            track_event(user_id=user,event_name="experience_selected",job_id=job_id,experience_id=experience.id,status="success")
        context=self._context(db,user,question);language=response_language(profile_repo.get(db,user));qh=_hash(f"{question.question}|{question.category}");eh=fingerprint(experience_source(experience)) if experience else None;jh=_hash(context["text"])
        version=f"{ANSWER_VERSION}-{length}"
        cached=interview_answers_repo.current(db,user,question.id,experience.id if experience else None,qh,eh,jh,language,version)
        if cached and not regenerate:return {**serialize_model(cached),"cached":True}
        exp_data=serialize_model(experience) if experience else None
        generated=ai_client.structured_completion(prompt_name="interview_answer",schema=AnswerOutput,payload={"response_language":language,"answer_length":length,"question":serialize_model(question),"selected_experience":exp_data,"job_context":context["text"],"technical_conceptual":technical})
        grounding=f"{question.question}\n{context['text']}\n{experience_source(experience) if experience else ''}"
        values={key:_strip_unsupported_technologies(_strip_unsupported_numbers(value,grounding),grounding) for key,value in generated.model_dump().items()}
        row=interview_answers_repo.create(db,{"user_id":user,"question_id":question.id,"experience_id":experience.id if experience else None,**values,"response_language":language,"follow_up_questions":[],"question_fingerprint":qh,"experience_fingerprint":eh,"job_fingerprint":jh,"answer_version":version})
        db.commit()
        track_event(user_id=user,event_name="interview_answer_regenerated" if regenerate else "interview_answer_generated",job_id=job_id,experience_id=experience.id if experience else None,status="success",latency_ms=elapsed_ms(started),metadata={"language":language})
        return {**serialize_model(row),"cached":False}
    def feedback(self,db,user,question_id,answer,experience_id,answer_id):
        question=self._question(db,user,question_id);experience=experiences_repo.get(db,user,experience_id) if experience_id else None
        if experience_id and not experience:raise KeyError("Experience not found")
        context=self._context(db,user,question);language=response_language(profile_repo.get(db,user));grounding=f"{answer}\n{question.question}\n{context['text']}\n{experience_source(experience) if experience else ''}"
        feedback_hash=_hash(f"{answer}|{experience_source(experience) if experience else ''}|{context['text']}|{language}|{FEEDBACK_VERSION}")
        stored=None
        if answer_id:
            answer_row=interview_answers_repo.get(db,user,answer_id)
            if not answer_row:raise KeyError("Answer not found")
            stored=answer_row.feedback
        else:stored=question.ai_feedback
        if stored and stored.get("fingerprint")==feedback_hash:return {**stored["result"],"cached":True}
        result=ai_client.structured_completion(prompt_name="interview_feedback",schema=FeedbackOutput,payload={"response_language":language,"question":serialize_model(question),"answer":answer,"selected_experience":serialize_model(experience) if experience else None,"job_context":context["text"]})
        data=result.model_dump();data["improved_answer"]=_strip_unsupported_technologies(_strip_unsupported_numbers(data["improved_answer"],grounding),grounding) or ""
        wrapped={"fingerprint":feedback_hash,"version":FEEDBACK_VERSION,"language":language,"result":data}
        if answer_id:
            answer_row.feedback=wrapped;answer_row.follow_up_questions=data["follow_up_questions"]
        else:question.user_answer=answer;question.ai_feedback=wrapped
        db.commit();return {**data,"cached":False}
    def _question(self,db,user,id):
        row=interview_questions_repo.get(db,user,id)
        if not row:raise KeyError("Question not found")
        return row
    def _validate_links(self,db,user,payload):
        if payload.get("application_id") and not applications_repo.get(db,user,payload["application_id"]):raise KeyError("Application not found")
        if payload.get("interview_id") and not interviews_repo.get(db,user,payload["interview_id"]):raise KeyError("Interview not found")
    def _context(self,db,user,question):
        app=applications_repo.get(db,user,question.application_id) if question.application_id else None;job=jobs_repo.get_row(db,user,app.job_id) if app and app.job_id else None
        return {"text":job_source(job) if job else " ".join(filter(None,[question.company,question.role,app.company if app else None,app.role if app else None]))}
    def _technical(self,question):return question.category.casefold() in TECHNICAL_CATEGORIES and not any(cue in question.question.casefold() for cue in PERSONAL_CUES)

interview_service=InterviewService()
