"""Инструменты агента для сценария «Первые недели и чек-лист» (спека 101, задача T4).

Логика и права — в имитациях сервисов `app.mcp_server` (зона Codex): функции сами проверяют, кто
что может. Здесь — только описание инструментов для модели и короткие ответы без лишних полей.
Права `ROLE_PERMISSIONS` решают, какие инструменты вообще показать модели; точную проверку
(свой стажёр, свой пункт) делает сервис.

Изменение уровня навыка (`set_skill_level`) намеренно НЕ инструмент: уровень меняет только
наставник руками, ИИ человека не оценивает (SPEC, раздел 4).
"""
from functools import cache
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from app.mcp_server import access, checklist, hiring
from app.mcp_server.errors import Conflict, Forbidden, NotFound
from app.mcp_server.models import PlanItem
from app.mcp_server.seed import load_seed

from .tools import FORBIDDEN_MESSAGE, Tool, ToolRegistry
from .users import DEMO_USERS, Role, User, can_view_intern

DOMAIN_ERRORS = (NotFound, Forbidden, Conflict, ValidationError)


def domain_error(exc: Exception) -> dict[str, Any]:
    """Ошибку сервиса — в понятный модели ответ. Чужое и отсутствующее неразличимы."""
    if isinstance(exc, (NotFound, Forbidden)):
        return {"error": "forbidden", "message": FORBIDDEN_MESSAGE}
    if isinstance(exc, Conflict):
        return {"error": "conflict", "message": str(exc)}
    return {"error": "invalid_arguments", "message": "Неверные данные для сервиса."}


@cache
def resource_titles() -> dict[str, str]:
    return {r.id: r.title for r in load_seed().resources.values()}


def _item_brief(item: PlanItem) -> dict[str, Any]:
    return {
        "id": item.id, "title": item.title, "stage": item.stage, "status": item.status,
        "owner_role": item.owner_role, "due_day": item.due_day, "overdue": item.overdue,
        "resource_id": item.resource_id, "topic": item.topic, "practice": item.practice,
        "waiting_for": item.waiting_for, "waiting_days": item.waiting_days, "status_reason": item.status_reason,
    }


def _target(user: User, intern_id: str | None) -> str:
    return intern_id or user.id


async def _safe(coro):
    try:
        return await coro
    except DOMAIN_ERRORS as exc:
        return domain_error(exc)


# --- План -----------------------------------------------------------------------------------------

class PlanArgs(BaseModel):
    intern_id: str | None = Field(default=None, description="id стажёра; не указывай, если это свой план")


async def get_plan(user: User, args: PlanArgs) -> dict:
    async def run():
        plan = await checklist.get_plan(user, _target(user, args.intern_id))
        return {
            "intern_id": plan.intern_id,
            "current_day": plan.current_day,
            "ladder": [s.model_dump() for s in plan.ladder],
            "next_step": _item_brief(plan.next_step.item) if plan.next_step.item else None,
            "waiting": [_item_brief(i) for i in plan.next_step.waiting],
            "items": [_item_brief(i) for i in plan.items if i.stage in ("week1", "week2")],
            "ahead": [i.title for i in plan.items if i.stage not in ("week1", "week2")],
        }
    return await _safe(run())


class StatusArgs(BaseModel):
    item_id: str = Field(description="id пункта плана, например anya.w1.notes")
    status: Literal["in_progress", "done"] = Field(description="новый статус")
    reason: str | None = Field(default=None, max_length=300, description="причина — обязательна, если наставник возвращает пункт")


async def set_plan_item_status(user: User, args: StatusArgs) -> dict:
    async def run():
        item = await checklist.set_item_status(user, args.item_id, args.status, args.reason)
        return {"status": "updated", "item": _item_brief(item)}
    return await _safe(run())


# --- Доступы --------------------------------------------------------------------------------------

class NoArgs(BaseModel):
    pass


async def list_access_resources(user: User, args: NoArgs) -> dict:
    async def run():
        return {"resources": [r.model_dump(mode="json") for r in await access.list_resources(user)]}
    return await _safe(run())


class RequestArgs(BaseModel):
    resource_id: str = Field(description="id ресурса из list_access_resources")
    level: Literal["read", "edit", "admin"] = Field(
        default="read", description="уровень прав; стажёру предлагай минимально достаточный — read")
    justification: str = Field(min_length=3, max_length=300, description="обоснование заявки")


LEVEL_TITLES = {"read": "чтение", "edit": "редактирование", "admin": "администрирование"}


async def resource_visible(user: User, args: RequestArgs) -> bool:
    """Ресурс есть в списке, доступном стажёру (своя команда или общий). Чужой — как несуществующий."""
    try:
        return any(r.id == args.resource_id for r in await access.list_resources(user))
    except DOMAIN_ERRORS:
        return False


async def create_access_request(user: User, args: RequestArgs) -> dict:
    async def run():
        req = await access.create_request(user, args.resource_id, args.level, args.justification)
        return {"status": "created", "request": req.model_dump(mode="json")}
    return await _safe(run())


class RequestsArgs(BaseModel):
    intern_id: str | None = Field(default=None, description="id стажёра (для наставника); не указывай для своих заявок")


async def list_access_requests(user: User, args: RequestsArgs) -> dict:
    async def run():
        reqs = await access.list_requests(user, args.intern_id)
        return {"requests": [r.model_dump(mode="json") for r in reqs]}
    return await _safe(run())


class DecideArgs(BaseModel):
    request_id: str = Field(description="номер заявки, например REQ-1002")
    approve: bool = Field(description="true — одобрить, false — отклонить")
    reason: str | None = Field(default=None, max_length=300, description="причина — обязательна при отказе")


async def decide_access_request(user: User, args: DecideArgs) -> dict:
    async def run():
        req = await access.decide_request(user, args.request_id, args.approve, args.reason)
        return {"status": "decided", "request": req.model_dump(mode="json")}
    return await _safe(run())


# --- Профиль --------------------------------------------------------------------------------------

async def get_skill_profile(user: User, args: PlanArgs) -> dict:
    async def run():
        profile = await hiring.get_skill_profile(user, _target(user, args.intern_id))
        return profile.model_dump(mode="json", exclude={"updated_by", "updated_at"})
    return await _safe(run())


def register_onboarding_tools(registry: ToolRegistry) -> None:
    registry.register(Tool(
        name="get_plan",
        description="План стажёра: день стажировки, этапы, пункты недель 1–2 со статусами, следующий шаг и кого ждём.",
        args_model=PlanArgs, permission="plan:read", handler=get_plan,
    ))
    registry.register(Tool(
        name="set_plan_item_status",
        description=("Отметить пункт плана: done — сделано, in_progress — вернуть в работу (наставник, с причиной). "
                     "Пункты с доступами закрываются только заявкой. Выполняется после подтверждения."),
        args_model=StatusArgs, permission="plan:write", handler=set_plan_item_status, kind="write",
        describe=lambda a: f"Пункт плана {a.item_id}: {'сделано' if a.status == 'done' else 'вернуть в работу'}",
    ))
    registry.register(Tool(
        name="list_access_resources",
        description="Ресурсы, на которые стажёр может подать заявку на доступ (Jira, Confluence, пространство команды).",
        args_model=NoArgs, permission="access:request", handler=list_access_resources,
    ))
    registry.register(Tool(
        name="create_access_request",
        description=("Подать заявку на доступ от имени стажёра. Предлагай уровень read. "
                     "Выполняется только после подтверждения стажёром."),
        args_model=RequestArgs, permission="access:request", handler=create_access_request, kind="write",
        describe=lambda a: (f"Заявка на доступ: {resource_titles().get(a.resource_id, a.resource_id)}, "
                            f"права — {LEVEL_TITLES[a.level]}"),
        precheck=resource_visible,
    ))
    registry.register(Tool(
        name="list_access_requests",
        description="Заявки на доступ: свои (стажёр) или своих стажёров (наставник), новые сверху.",
        args_model=RequestsArgs, permission="access:read", handler=list_access_requests,
    ))
    registry.register(Tool(
        name="decide_access_request",
        description="Одобрить или отклонить заявку стажёра (только наставник-согласующий). Выполняется после подтверждения.",
        args_model=DecideArgs, permission="access:approve", handler=decide_access_request, kind="write",
        describe=lambda a: f"{'Одобрить' if a.approve else 'Отклонить'} заявку {a.request_id}",
    ))
    registry.register(Tool(
        name="get_skill_profile",
        description="Карта навыков стажёра по темам (новичок / знаком / уверенно), сильные стороны и темы для роста.",
        args_model=PlanArgs, permission="skills:read", handler=get_skill_profile,
    ))


async def plan_context(user: User) -> str:
    """Короткая сводка для системного промпта: стажёру — его день, следующий шаг и уровень по темам;
    наставнику, руководителю и куратору — каких стажёров он видит (id для инструментов)."""
    if user.role in (Role.MENTOR, Role.LEAD, Role.CURATOR):
        visible = [u for u in DEMO_USERS.values() if u.role == Role.INTERN and can_view_intern(user, u)]
        if not visible:
            return ""
        names = ", ".join(f"{u.name} (intern_id {u.id})" for u in visible)
        return f"\n\nСтажёры, чьи планы тебе доступны: {names}. Для их плана вызывай get_plan с intern_id."
    if user.role != Role.INTERN:
        return ""
    try:
        plan = await checklist.get_plan(user, user.id)
        profile = await hiring.get_skill_profile(user, user.id)
    except DOMAIN_ERRORS:
        return ""
    lines = [f"\n\nПлан стажёра: день {plan.current_day}."]
    mentor = DEMO_USERS.get(user.mentor_id or "")
    if mentor:
        lines.append(f"Наставник: {mentor.name}.")
    if plan.next_step.item:
        lines.append(f"Следующий шаг: «{plan.next_step.item.title}» (id {plan.next_step.item.id}).")
    for w in plan.next_step.waiting:
        who = DEMO_USERS.get(w.waiting_for or "")
        lines.append(f"Ждёт другого человека ({who.name if who else 'согласующий'}): «{w.title}», {w.waiting_days or 0} дн.")
    levels = {"novice": "новичок", "familiar": "знаком", "confident": "уверенно"}
    if profile.skills:
        lines.append("Уровень по темам: " + ", ".join(f"{k} — {levels[v]}" for k, v in profile.skills.items()) + ".")
    return " ".join(lines)
