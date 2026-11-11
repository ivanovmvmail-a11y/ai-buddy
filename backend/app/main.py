"""HTTP API AI-buddy (Flask). Контракт — docs/API.md."""
import logging
import time
from typing import Literal

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, ValidationError

from app import async_runner
from app.agent import analytics, service
from app.agent.actions import Action
from app.agent.users import get_user
from app.config import settings
from app.llm import Message
from app.onboarding_api import bp as onboarding_bp

USER_HEADER = "X-User-Id"
log = logging.getLogger("ai_buddy.api")


class ChatMessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn]


class Source(BaseModel):
    title: str
    url: str | None = None


class ChatResponse(BaseModel):
    answer_id: str | None = None  # для оценки «полезно / не полезно» (спека 302)
    reply: str
    sources: list[Source] = []
    actions: list[Action] = []


def _action_json(action: Action) -> dict:
    return action.model_dump(mode="json")


def create_app() -> Flask:
    app = Flask(__name__)
    app.json.ensure_ascii = False  # кириллица в ответах как есть, без \uXXXX

    origins = [o.strip() for o in settings.frontend_origins.split(",") if o.strip()]
    CORS(app, origins=origins, allow_headers=["Content-Type", USER_HEADER])

    @app.before_request
    def load_user():
        # ИМИТАЦИЯ авторизации: в Авито пользователь берётся из корпоративного SSO.
        if request.endpoint in (None, "health") or request.method == "OPTIONS":
            return None
        user = get_user(request.headers.get(USER_HEADER))
        if user is None:
            return jsonify(detail="Неизвестный пользователь"), 401
        g.user = user
        return None

    @app.errorhandler(service.ActionError)
    def action_error(exc: service.ActionError):
        return jsonify(detail=str(exc)), exc.status

    @app.get("/health")
    def health():
        return {"status": "ok", "llm_provider": settings.llm_provider}

    @app.get("/me")
    def me():
        return g.user.model_dump(mode="json")

    @app.post("/chat")
    def chat():
        try:
            req = ChatRequest.model_validate(request.get_json(silent=True) or {})
        except ValidationError as exc:
            return jsonify(detail=exc.errors(include_url=False, include_context=False)), 422

        # системные сообщения от клиента не принимаем — системный промпт задаёт только сервер
        history = [Message(role=m.role, content=m.content) for m in req.messages if m.role != "system"]
        started = time.perf_counter()
        try:
            result = async_runner.run(service.agent.answer(history, g.user))
        except Exception:
            # детали — только в лог сервера; пользователю — общее сообщение без внутренностей
            log.exception("chat failed user=%s", g.user.id)
            return jsonify(detail="Помощник временно недоступен. Попробуйте ещё раз через минуту."), 502
        answer_id = analytics.new_answer_id()
        question = next((m.content for m in reversed(history) if m.role == "user"), "")
        async_runner.run(analytics.record_answer(
            g.user, answer_id=answer_id, question=question, reply=result.reply, sources=len(result.sources),
            tools=result.tools, refused=result.refused, drafts=len(result.actions),
            latency_ms=round((time.perf_counter() - started) * 1000),
        ))
        return ChatResponse(
            answer_id=answer_id,
            reply=result.reply,
            sources=[Source(**s) for s in result.sources],
            actions=result.actions,
        ).model_dump(mode="json")

    @app.get("/actions")
    def list_actions():
        return {"actions": [_action_json(a) for a in service.agent.list_actions(g.user)]}

    @app.post("/actions/<action_id>/confirm")
    def confirm_action(action_id: str):
        return _action_json(async_runner.run(service.agent.confirm(g.user, action_id)))

    @app.post("/actions/<action_id>/cancel")
    def cancel_action(action_id: str):
        return _action_json(service.agent.cancel(g.user, action_id))

    app.register_blueprint(onboarding_bp)
    return app


app = create_app()
