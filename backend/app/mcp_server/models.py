"""Публичные модели по plan.md §3.1 и снимок состояния для хранилища T1."""
from .self_check_models import SelfCheckResult

from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue

from app.agent.users import Role, User

Stage = Literal["week1", "week2", "month1", "month2", "after3m"]
OwnerRole = Literal["intern", "mentor", "lead"]
ItemStatus = Literal["not_started", "in_progress", "waiting", "done"]
SkillLevel = Literal["novice", "familiar", "confident"]
AccessLevel = Literal["read", "edit", "admin"]
RequestStatus = Literal["created", "pending_approval", "granted", "rejected"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SystemActor(BaseModel):
    """Внутренний субъект, не пользователь/роль агента и не входная HTTP-модель."""
    model_config = ConfigDict(frozen=True, extra="forbid")
    id: Literal["system"] = "system"
    role: Literal["system"] = "system"
    team: Literal["system"] = "system"
    name: str = "Система демо"


Actor = User | SystemActor


class PlanItem(Model):
    id: str
    intern_id: str
    stage: Stage
    order: int = Field(ge=0)
    title: str
    summary: str
    owner_role: OwnerRole
    topic: str | None = None
    doc_source_id: str | None = None
    resource_id: str | None = None
    due_day: int | None = Field(default=None, ge=1)
    practice: str | None = None
    status: ItemStatus = "not_started"
    status_reason: str | None = None
    updated_at: AwareDatetime
    updated_by: str | None = None
    overdue: bool = False
    waiting_for: str | None = None
    waiting_days: int | None = Field(default=None, ge=0)


class StageInfo(Model):
    stage: Stage
    title: str
    total: int
    done: int
    state: Literal["passed", "current", "ahead"]


class NextStep(Model):
    item: PlanItem | None
    waiting: list[PlanItem]


class Plan(Model):
    intern_id: str
    current_day: int = Field(ge=1)
    items: list[PlanItem]
    ladder: list[StageInfo]
    next_step: NextStep


class AccessResource(Model):
    id: str
    title: str
    kind: Literal["base", "team_space"]
    team: str | None = None
    approver: Literal["auto", "mentor"]
    fields: list[dict]


class AccessRequest(Model):
    id: str
    intern_id: str
    resource_id: str
    level: AccessLevel = "read"
    justification: str
    status: RequestStatus
    approver_id: str | None = None
    reject_reason: str | None = None
    plan_item_id: str | None = None
    created_day: int = Field(ge=1)
    created_at: AwareDatetime
    updated_at: AwareDatetime


class SkillProfile(Model):
    intern_id: str
    skills: dict[str, SkillLevel]
    strengths: list[str]
    growth: list[str]
    updated_by: str | None = None
    updated_at: AwareDatetime


class Reminder(Model):
    id: str
    user_id: str
    plan_item_id: str | None = None
    request_id: str | None = None
    text: str
    status: Literal["active", "snoozed", "done"] = "active"
    created_day: int = Field(ge=1)
    snooze_until_day: int | None = None


class InternState(Model):
    intern_id: str
    start_date: date
    current_day: int = Field(ge=1)


class Event(Model):
    ts: datetime
    user_id: str
    role: Role | Literal["system"]
    team: str
    type: str
    payload: dict[str, JsonValue]


class ActionDraft(Model):
    id: str
    owner_id: str
    action: str
    payload: dict[str, JsonValue]
    status: Literal["pending", "confirmed", "cancelled"] = "pending"
    result_id: str | None = None


class OnboardingData(Model):
    interns: dict[str, InternState] = Field(default_factory=dict)
    items: dict[str, PlanItem] = Field(default_factory=dict)
    resources: dict[str, AccessResource] = Field(default_factory=dict)
    requests: dict[str, AccessRequest] = Field(default_factory=dict)
    self_check_attempts: dict[str, SelfCheckResult] = Field(default_factory=dict)
    profiles: dict[str, SkillProfile] = Field(default_factory=dict)
    reminders: dict[str, Reminder] = Field(default_factory=dict)
    drafts: dict[str, ActionDraft] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
