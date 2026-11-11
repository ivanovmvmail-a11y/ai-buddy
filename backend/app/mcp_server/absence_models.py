"""Отгул на один день: закрытый список причин, без свободных медицинских полей."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool

AbsenceReason = Literal['personal', 'family', 'study']
REASONS = {'personal': 'Личные дела', 'family': 'Семейные дела', 'study': 'Учебные дела'}

class AbsenceInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    day: date
    reason: AbsenceReason

class DecisionInput(BaseModel):
    approve: StrictBool

class AbsenceRequest(AbsenceInput):
    model_config = ConfigDict(extra='forbid', validate_assignment=True)
    id: str
    intern_id: str
    lead_id: str
    team: str
    created_day: int = Field(ge=1)
    status: Literal['pending', 'approved', 'rejected'] = 'pending'
    decided_day: int | None = Field(default=None, ge=1)

class AbsenceFact(BaseModel):
    """Проекция для наставника: ни причины, ни id заявки, ни истории решений."""
    intern_id: str
    day: date
