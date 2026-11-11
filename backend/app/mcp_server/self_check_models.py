"""Публичные вопросы, приватные ответы банка и личный разбор без рейтинга."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

Topic = Literal['git','sql','ci']
Index = Annotated[StrictInt, Field(ge=0)]

class Question(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    topic: Topic
    prompt: str = Field(min_length=1)
    options: list[str] = Field(min_length=2, max_length=6)
    source_id: str
    source_url: str

class BankQuestion(Question):
    team: str
    correct_index: Index
    explanation: str = Field(min_length=1)

    @model_validator(mode='after')
    def valid_index(self):
        if self.correct_index >= len(self.options):
            raise ValueError('Правильный вариант отсутствует в вопросе')
        return self

class Submission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    topic: Topic
    answers: dict[str, Index] = Field(min_length=2, max_length=3)

class ReviewedAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: str
    prompt: str
    options: list[str]
    selected_index: Index
    correct_index: Index
    explanation: str
    source_id: str
    source_url: str

class SelfCheckResult(BaseModel):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    id: str
    intern_id: str
    team: str
    topic: Topic
    completed_day: int = Field(ge=1)
    review: list[ReviewedAnswer] = Field(min_length=2, max_length=3)
