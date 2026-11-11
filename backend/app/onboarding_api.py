"""HTTP для экрана «план + чат» (спека 101, задача T4). Контракт — docs/API.md, раздел «Онбординг».

Эндпоинты — тонкий слой над имитациями сервисов `app.mcp_server` (зона Codex): права проверяют сами
функции сервисов. Кнопки интерфейса, которые нажимает человек («Готово», «Одобрить»), выполняются сразу —
это и есть решение человека. Действия, которые готовит ИИ или кнопка «Сделать за меня», идут через
черновик и `POST /actions/{id}/confirm`.
"""
import hmac
import logging
import time
from urllib.parse import unquote
from typing import Literal

from flask import Blueprint, g, jsonify, request
from pydantic import BaseModel, Field, StrictBool, ValidationError
from pydantic_core import to_jsonable_python

from app import async_runner
from app.config import settings
from app.http_body import json_body
from app.agent import analytics, explain, history, service
from app.agent.onboarding_tools import resource_titles
from app.agent.users import DEMO_USERS, Role, can_view_intern
from app.mcp_server import absence, access, checklist, clock, hiring
from app.mcp_server.absence_models import REASONS
from app.mcp_server.errors import Conflict, Forbidden, NotFound

bp = Blueprint("onboarding", __name__)
log = logging.getLogger("ai_buddy.onboarding_api")

PLAN_ROLES = {Role.INTERN, Role.MENTOR, Role.LEAD, Role.CURATOR}


def _json(model) -> dict:
    return model.model_dump(mode="json")


def _body(model: type[BaseModel]) -> BaseModel:
    return model.model_validate(json_body())


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
    titles = resource_titles()  # наставнику справочник ресурсов не выдаётся — название кладём в заявку
    return {"requests": [{**_json(r), "resource_title": titles.get(r.resource_id, r.resource_id)} for r in reqs]}


class DecideIn(BaseModel):
    approve: StrictBool  # «yes», 1 и т. п. согласием не считаются
    reason: str | None = None


@bp.post("/access/requests/<request_id>/decide")
def decide(request_id: str):
    body = _body(DecideIn)
    return _json(async_runner.run(access.decide_request(g.user, request_id, body.approve, body.reason)))


# --- Отгул на один день (SPEC 3.8; сервис — app/mcp_server/absence.py) ----------------------------

def _absence(r) -> dict:
    intern = DEMO_USERS.get(r.intern_id)
    return {**_json(r), "intern_name": intern.name if intern else r.intern_id, "reason_title": REASONS[r.reason]}


@bp.get("/absence/requests")
def absence_requests():
    """Стажёр — свои заявки, руководитель — своей команды; остальным 404 (решает сервис)."""
    reqs = async_runner.run(absence.list_requests(g.user.id))
    return {"requests": [_absence(r) for r in sorted(reqs, key=lambda r: r.created_day, reverse=True)]}


class AbsenceDecideIn(BaseModel):
    approve: StrictBool


@bp.post("/absence/requests/<request_id>/decide")
def absence_decide(request_id: str):
    """Кнопка руководителя — это и есть решение человека: черновик сервиса готовится и подтверждается сразу."""
    body = _body(AbsenceDecideIn)

    async def run():
        draft = await absence.draft_decision(g.user.id, request_id, body.approve)
        return await absence.confirm_decision(g.user.id, draft.id)
    return _absence(async_runner.run(run()))


@bp.get("/absence/facts")
def absence_facts():
    """Наставнику — только «отсутствует <дата>» своего стажёра: без причины и номера заявки."""
    intern_id = request.args.get("intern_id")
    if not intern_id:
        raise NotFound()
    return {"facts": [_json(f) for f in async_runner.run(absence.list_absence_facts(g.user.id, intern_id))]}


# --- Профиль и напоминания ------------------------------------------------------------------------

@bp.get("/profile/skills")
def skills():
    return _json(async_runner.run(hiring.get_skill_profile(g.user, _intern_id())))


class SkillIn(BaseModel):
    intern_id: str
    topic: str = Field(min_length=1, max_length=40)
    level: Literal["novice", "familiar", "confident"]


@bp.post("/profile/skills")
def set_skill():
    """Спека 104: уровень меняет только наставник этого стажёра — это решение человека, не ИИ."""
    body = _body(SkillIn)
    return _json(async_runner.run(hiring.set_skill_level(g.user, body.intern_id, body.topic, body.level)))


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


# --- Оценка ответов и метрики (спека 302) ----------------------------------------------------------

class FeedbackIn(BaseModel):
    answer_id: str
    useful: bool


@bp.post("/feedback")
def feedback():
    body = _body(FeedbackIn)
    async_runner.run(analytics.record_feedback(g.user, body.answer_id, body.useful))
    return "", 204


class ExplainIn(BaseModel):
    kind: Literal["explain", "steps", "who"] = "explain"


@bp.post("/plan/items/<item_id>/explained")
def item_explained(item_id: str):
    """Без модели: объяснение пункта, «по шагам» или «к кому идти» — из документа пункта и оргструктуры
    (app/agent/explain.py). Ответ записывается в события, чтобы метрики и оценка его видели."""
    started = time.perf_counter()
    body = _body(ExplainIn)
    result = async_runner.run(explain.explain_item(g.user, _intern_id(), item_id, body.kind))  # чужой пункт — 404
    answer_id = analytics.new_answer_id()
    async_runner.run(analytics.record_explained(
        g.user, answer_id=answer_id, title=result["title"], with_source=result["with_source"],
        latency_ms=round((time.perf_counter() - started) * 1000),
    ))
    asked = {"explain": f"Объясни пункт «{result['title']}»", "steps": explain.CHIPS["steps"], "who": explain.CHIPS["who"]}
    try:
        async_runner.run(history.record_turn(
            g.user.id, asked[body.kind], result["text"], sources=[result["source"]] if result["source"] else [],
            answer_id=answer_id, scripted=True))
    except Exception:
        log.exception("chat history not saved user=%s", g.user.id)
    return jsonify(answer_id=answer_id, text=result["text"], source=result["source"], chips=result["chips"]), 201


@bp.get("/metrics")
def metrics_view():
    return jsonify(async_runner.run(analytics.metrics(g.user, request.args.get("intern_id"))))


# --- Черновик по кнопке ---------------------------------------------------------------------------

class DraftIn(BaseModel):
    tool: str
    params: dict = Field(default_factory=dict)


@bp.post("/actions")
def create_draft():
    """«Сделать за меня»: черновик write-инструмента без модели. Выполнение — POST /actions/{id}/confirm."""
    body = _body(DraftIn)
    return _json(async_runner.run(service.agent.draft(g.user, body.tool, body.params))), 201


# --- Демо-панель (явно помечена в интерфейсе как инструмент демонстрации) -------------------------

class NextDayIn(BaseModel):
    intern_id: str | None = None


DEMO_KEY_HEADER = "X-Demo-Key"
DEMO_KEY_REQUIRED = "Нужно код-слово демо"


def _demo_key_error():
    """Публичный сайт: без код-слова посетитель не сбросит данные посреди показа (аудит D6)."""
    expected = settings.demo_key
    if not expected:
        return None
    # Браузер не пропускает кириллицу в заголовке — интерфейс шлёт encodeURIComponent(код-слово).
    given = unquote(request.headers.get(DEMO_KEY_HEADER, ""))
    if hmac.compare_digest(given.encode(), expected.encode()):
        return None
    return jsonify(detail=DEMO_KEY_REQUIRED), 403


@bp.post("/demo/next-day")
def next_day():
    if (denied := _demo_key_error()) is not None:
        return denied
    body = _body(NextDayIn)
    return {"days": async_runner.run(clock.advance_day(g.user, body.intern_id))}


@bp.post("/demo/reset")
def reset():
    if (denied := _demo_key_error()) is not None:
        return denied
    async_runner.run(clock.reset_demo(g.user))
    async_runner.run(service.agent.store.clear())
    async_runner.run(history.history.clear())  # черновики старого прогона ссылались бы на сброшенные данные
    return {"status": "reset"}
