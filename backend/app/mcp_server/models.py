"""Публичные модели по plan.md §3.1 и снимок состояния для хранилища T1."""
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue, PrivateAttr, model_validator

from app.agent.users import Role, User
from .absence_models import AbsenceRequest

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
    kind: Literal["common", "personal"] = "common"
    reason: str | None = None
    skill_level: SkillLevel | None = None
    known_marked: bool = False
    catalog_key: str | None = None
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


class CatalogItem(Model):
    key: str
    team: str
    topic: str
    topic_title: str
    level: Literal["novice"] = "novice"
    title: str
    summary: str
    doc_source_id: str
    practice: str
    stage: Literal["week1", "week2"]
    due_offset: int = Field(ge=1)
    in_plan: bool = False


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


SuggestionStatus = Literal["pending", "accepted", "dismissed"]


class SkillSuggestion(Model):
    id: str
    intern_id: str
    mentor_id: str
    intern_name: str = ""
    topic: str
    topic_title: str = ""
    from_level: SkillLevel
    to_level: SkillLevel
    basis: str
    evidence: list[str] = Field(default_factory=list, exclude=True)
    created_day: int = Field(ge=1)
    status: SuggestionStatus = "pending"
    decided_day: int | None = Field(default=None, ge=1)


ReminderKind = Literal["plan_item", "access_request", "skill_changed", "personal_item_added",
                       "skill_suggestion", "absence_pending", "absence_decided", "absence_today",
                       "absence_new", "absence_fact"]


class ReminderAction(Model):
    label: str
    target: Literal["plan", "plan_item", "access_request", "skill_suggestion", "absence_request", "intern"]


class Reminder(Model):
    id: str
    user_id: str
    kind: ReminderKind = "plan_item"
    action: ReminderAction | None = None
    intern_id: str | None = None
    absence_request_id: str | None = None
    suggestion_id: str | None = None
    plan_item_id: str | None = None
    request_id: str | None = None
    text: str
    status: Literal["active", "snoozed", "done"] = "active"
    created_day: int = Field(ge=1)
    snooze_until_day: int | None = None

    @model_validator(mode="before")
    @classmethod
    def legacy_kind(cls, value):
        if isinstance(value, dict) and "kind" not in value:
            value = {**value, "kind": "access_request" if value.get("request_id") else "plan_item"}
        return value


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
    # Возможность конкретной SQL-транзакции, не поле публичного DTO или seed.
    _suggestions_available: bool = PrivateAttr(default=True)

    interns: dict[str, InternState] = Field(default_factory=dict)
    items: dict[str, PlanItem] = Field(default_factory=dict)
    resources: dict[str, AccessResource] = Field(default_factory=dict)
    absence_requests: dict[str, AbsenceRequest] = Field(default_factory=dict)
    drafts: dict[str, ActionDraft] = Field(default_factory=dict)
    requests: dict[str, AccessRequest] = Field(default_factory=dict)
    profiles: dict[str, SkillProfile] = Field(default_factory=dict)
    reminders: dict[str, Reminder] = Field(default_factory=dict)
    suggestions: dict[str, SkillSuggestion] = Field(default_factory=dict)
    personal_catalog: dict[str, CatalogItem] = Field(default_factory=dict)
    events: list[Event] = Field(default_factory=list)
