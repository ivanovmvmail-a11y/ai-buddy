"""Общие правила доступа и расчёты; публичные сервисы проверяют их в транзакции."""
from datetime import datetime, time, timedelta, timezone
from typing import Annotated

from pydantic import Field, StrictBool, StringConstraints, TypeAdapter

from app.agent.users import DEMO_USERS, Role, User, can_view_intern

from .errors import NotFound
from .models import AccessLevel, ItemStatus, OnboardingData, PlanItem, SkillLevel, SuggestionStatus

WORK_STAGES = ("week1", "week2")
STAGES = (*WORK_STAGES, "month1", "month2", "after3m")
nonempty = TypeAdapter(Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)])
positive = TypeAdapter(Annotated[int, Field(ge=1, strict=True)])
item_status = TypeAdapter(ItemStatus)
access_level = TypeAdapter(AccessLevel)
skill_level = TypeAdapter(SkillLevel)
suggestion_status = TypeAdapter(SuggestionStatus)
strict_bool = TypeAdapter(StrictBool)


def known_actor(actor: User):
    if DEMO_USERS.get(actor.id) != actor:
        raise NotFound()


def intern(data: OnboardingData, intern_id: str) -> User:
    user = DEMO_USERS.get(intern_id)
    if user is None or user.role != Role.INTERN or intern_id not in data.interns:
        raise NotFound()
    return user


def can_read_plan(actor: User, target: User) -> bool:
    # Ограничение видимости сервиса + общая проверка связи пользователя со стажёром.
    return actor.role in {Role.INTERN, Role.MENTOR, Role.LEAD, Role.CURATOR} and can_view_intern(actor, target)


def can_read_private(actor: User, target: User) -> bool:
    return actor.role in {Role.INTERN, Role.MENTOR} and can_view_intern(actor, target)


def require_intern(data: OnboardingData, actor: User, intern_id: str, *, private=False) -> User:
    known_actor(actor)
    target = intern(data, intern_id)
    if not (can_read_private if private else can_read_plan)(actor, target):
        raise NotFound()
    return target


def timestamp(data: OnboardingData, intern_id: str, day: int | None = None) -> datetime:
    state = data.interns[intern_id]
    # Демо-часы: день стажировки задаёт дату; реальные внешние часы не нужны.
    date = state.start_date + timedelta(days=(day or state.current_day) - 1)
    return datetime.combine(date, time(12), tzinfo=timezone.utc)


def item_view(data: OnboardingData, item: PlanItem, day: int | None = None) -> PlanItem:
    state = data.interns[item.intern_id]
    current_day = state.current_day if day is None else day
    updated_day = (item.updated_at.astimezone(timezone.utc).date() - state.start_date).days + 1
    return item.model_copy(update={
        "skill_level": data.profiles[item.intern_id].skills.get(item.topic) if item.intern_id in data.profiles else None,
        "overdue": item.status != "done" and item.due_day is not None and current_day > item.due_day,
        "waiting_days": max(0, current_day - updated_day) if item.status == "waiting" else None,
    }, deep=True)


def owner_id(item: PlanItem) -> str:
    user = DEMO_USERS[item.intern_id]
    return {"intern": user.id, "mentor": user.mentor_id, "lead": user.lead_id}[item.owner_role]
