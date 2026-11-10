"""HTTP для экрана «план + чат» (спека 101, задача T4). Контракт — docs/API.md, раздел «Онбординг».

Эндпоинты — тонкий слой над имитациями сервисов `app.mcp_server` (зона Codex): права проверяют сами
функции сервисов. Кнопки интерфейса, которые нажимает человек («Готово», «Одобрить»), выполняются сразу —
это и есть решение человека. Действия, которые готовит ИИ или кнопка «Сделать за меня», идут через
черновик и `POST /actions/{id}/confirm`.
"""
from flask import Blueprint, g, jsonify, request
from pydantic import BaseModel, Field, ValidationError
from pydantic_core import to_jsonable_python

from app import async_runner
from app.agent import service
from app.agent.users import DEMO_USERS, Role, can_view_intern
from app.mcp_server import access, checklist, clock, hiring
from app.mcp_server.errors import Conflict, Forbidden, NotFound

bp = Blueprint("onboarding", __name__)

PLAN_ROLES = {Role.INTERN, Role.MENTOR, Role.LEAD, Role.CURATOR}


def _json(model) -> dict:
    return model.model_dump(mode="json")


def _body(model: type[BaseModel]) -> BaseModel:
    return model.model_validate(request.get_json(silent=True) or {})


def _intern_id() -> str:
    return request.args.get("intern_id") or g.user.id


@bp.errorhandler(NotFound)
def not_found(exc):
    return jsonify(detail="Не найдено"), 404


@bp.errorhandler(Forbidden)
def forbidden(exc):
    return jsonify(detail=str(exc)), 403


@bp.errorhandler(Conflict)
def conflict(exc):
    return jsonify(detail=str(exc)), 409


@bp.errorhandler(ValidationError)
def invalid(exc: ValidationError):
    return jsonify(detail=exc.errors(include_url=False, include_context=False, include_input=False)), 422


# --- План -----------------------------------------------------------------------------------------

@bp.get("/interns")
def interns():
    """Стажёры, чей план может открыть пользователь (для выбора в интерфейсе)."""
    user = g.user
    visible = [
        {"id": u.id, "name": u.name, "team": u.team}
        for u in DEMO_USERS.values()
        if u.role == Role.INTERN and user.role in PLAN_ROLES and can_view_intern(user, u)
    ]
    return {"interns": visible}


@bp.get("/plan")
def plan():
    return _json(async_runner.run(checklist.get_plan(g.user, _intern_id())))


class StatusIn(BaseModel):
    status: str
    reason: str | None = None


@bp.post("/plan/items/<item_id>/status")
def item_status(item_id: str):
    body = _body(StatusIn)
    return _json(async_runner.run(checklist.set_item_status(g.user, item_id, body.status, body.reason)))


@bp.get("/plan/summary")
def summary():
    week = request.args.get("week", type=int) or 1
    return jsonify(to_jsonable_python(async_runner.run(checklist.weekly_summary(g.user, _intern_id(), week))))


# --- Доступы --------------------------------------------------------------------------------------

@bp.get("/access/resources")
def resources():
    return {"resources": [_json(r) for r in async_runner.run(access.list_resources(g.user))]}


@bp.get("/access/requests")
def requests_list():
    reqs = async_runner.run(access.list_requests(g.user, request.args.get("intern_id")))
    return {"requests": [_json(r) for r in reqs]}


class DecideIn(BaseModel):
    approve: bool
    reason: str | None = None


@bp.post("/access/requests/<request_id>/decide")
def decide(request_id: str):
    body = _body(DecideIn)
    return _json(async_runner.run(access.decide_request(g.user, request_id, body.approve, body.reason)))


# --- Профиль и напоминания ------------------------------------------------------------------------

@bp.get("/profile/skills")
def skills():
    return _json(async_runner.run(hiring.get_skill_profile(g.user, _intern_id())))


@bp.get("/reminders")
def reminders():
    items = async_runner.run(clock.list_reminders(g.user))
    return {"reminders": [_json(r) for r in items if r.status == "active"]}


class SnoozeIn(BaseModel):
    days: int = Field(default=1, ge=1, le=14)


@bp.post("/reminders/<reminder_id>/snooze")
def snooze(reminder_id: str):
    body = _body(SnoozeIn)
    return _json(async_runner.run(clock.snooze_reminder(g.user, reminder_id, body.days)))


@bp.post("/reminders/<reminder_id>/done")
def reminder_done(reminder_id: str):
    return _json(async_runner.run(clock.done_reminder(g.user, reminder_id)))


# --- Черновик по кнопке ---------------------------------------------------------------------------

class DraftIn(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)


@bp.post("/actions")
def create_draft():
    """«Сделать за меня»: черновик write-инструмента без модели. Выполнение — POST /actions/{id}/confirm."""
    body = _body(DraftIn)
    return _json(service.agent.draft(g.user, body.tool, body.params)), 201


# --- Демо-панель (явно помечена в интерфейсе как инструмент демонстрации) -------------------------

class NextDayIn(BaseModel):
    intern_id: str | None = None


@bp.post("/demo/next-day")
def next_day():
    body = _body(NextDayIn)
    return {"days": async_runner.run(clock.advance_day(g.user, body.intern_id))}


@bp.post("/demo/reset")
def reset():
    async_runner.run(clock.reset_demo(g.user))
    return {"status": "reset"}
