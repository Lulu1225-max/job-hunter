from typing import Literal

from pydantic import BaseModel

QuestionType = Literal["experience", "knowledge", "motivation", "case"]


class QuestionTypeResult(BaseModel):
    question_type: QuestionType
