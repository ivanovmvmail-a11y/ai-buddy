"""Приватный вопрос наставнику и состояние согласованной публикации."""
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictBool


class QuestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=3000)


class AnswerInput(QuestionInput):
    text: str = Field(min_length=1, max_length=6000)
    publish: StrictBool = False


class MentorQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    id: str
    intern_id: str
    mentor_id: str
    team: str
    question: str
    created_day: int = Field(ge=1)
    status: Literal["pending", "answered"] = "pending"
    answer: str | None = None
    answered_day: int | None = Field(default=None, ge=1)
    answered_at: AwareDatetime | None = None
    publication_status: Literal["not_requested", "pending", "published"] = "not_requested"
    public_content: str | None = None
    source_id: str | None = None
