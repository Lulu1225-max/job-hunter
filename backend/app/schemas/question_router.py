from typing import Literal

from pydantic import BaseModel

QuestionType = Literal["behavioral", "knowledge", "motivation", "resume_based", "case"]


class QuestionTypeResult(BaseModel):
    question_type: QuestionType
