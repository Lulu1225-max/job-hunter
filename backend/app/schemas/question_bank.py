from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Category = Literal["Behavioral", "Product", "Technical", "HR", "Other"]
Source = Literal["manual", "interview_generated", "actual_interview"]


class QuestionBankCreate(BaseModel):
    question: str = Field(min_length=2, max_length=3000)
    answer: str | None = Field(default=None, max_length=30000)
    category: Category = "Other"
    source: Source = "manual"
    replace_answer: bool = False


class QuestionBankUpdate(BaseModel):
    question: str | None = Field(default=None, min_length=2, max_length=3000)
    answer: str | None = Field(default=None, max_length=30000)
    category: Category | None = None


class FavoriteUpdate(BaseModel):
    is_favorite: bool
