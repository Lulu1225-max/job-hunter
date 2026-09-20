from __future__ import annotations
from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field

QuestionSource=Literal["public_research","ai_generated","user_added","actual_interview"]
Outcome=Literal["pending","passed","rejected","offer"]

class QuestionCreate(BaseModel):
    question:str=Field(min_length=2,max_length=3000);category:str=Field(default="other",max_length=80);source:QuestionSource="user_added";notes:str|None=None;application_id:UUID|None=None;interview_id:UUID|None=None
class QuestionList(BaseModel):
    questions:list[QuestionCreate]=Field(min_length=1,max_length=8)
class ParsedQuestion(BaseModel):
    question:str;category:str="other";source_excerpt:str
class ParsedQuestions(BaseModel):
    questions:list[ParsedQuestion]=Field(default_factory=list,max_length=30)
class ParseQuestionsRequest(BaseModel): text:str=Field(min_length=10,max_length=30000)
class ConfirmQuestionsRequest(BaseModel): questions:list[QuestionCreate]=Field(min_length=1,max_length=30)
class GenerateQuestionsRequest(BaseModel): application_id:UUID;category:str|None=None;count:int=Field(default=5,ge=1,le=8)
class RetrieveForQuestionRequest(BaseModel): limit:int=Field(default=3,ge=1,le=5)
class GenerateAnswerRequest(BaseModel): experience_id:UUID|None=None;answer_length:Literal["30s","1min","2min"]="1min";regenerate:bool=False;question_type:Literal["behavioral","knowledge","motivation","resume_based","case"]|None=None

class AnswerOutput(BaseModel): answer_30s:str|None=None;answer_1min:str|None=None;answer_2min:str|None=None
class FeedbackOutput(BaseModel):
    strengths:list[str]=Field(default_factory=list);weaknesses:list[str]=Field(default_factory=list);missing_evidence:list[str]=Field(default_factory=list);structure:str;star_completeness:str;clarity:str;specificity:str;relevance:str;follow_up_questions:list[str]=Field(min_length=3,max_length=5);improved_answer:str
class FeedbackRequest(BaseModel): answer:str=Field(min_length=2,max_length=12000);experience_id:UUID|None=None;answer_id:UUID|None=None

class InterviewCreate(BaseModel):
    application_id:UUID;round:str|None=Field(default=None,max_length=80);interview_type:str|None=Field(default=None,max_length=80);scheduled_at:datetime|None=None;status:str="completed";notes:str|None=None;difficulty:int|None=Field(default=None,ge=1,le=5);confidence:int|None=Field(default=None,ge=1,le=5);interviewer_notes:str|None=None;went_well:str|None=None;to_improve:str|None=None;outcome:Outcome="pending";actual_questions:list[str]=Field(default_factory=list,max_length=30);request_id:UUID|None=None
class InterviewUpdate(BaseModel):
    round:str|None=None;interview_type:str|None=None;scheduled_at:datetime|None=None;status:str|None=None;notes:str|None=None;difficulty:int|None=Field(default=None,ge=1,le=5);confidence:int|None=Field(default=None,ge=1,le=5);interviewer_notes:str|None=None;went_well:str|None=None;to_improve:str|None=None;outcome:Outcome|None=None
