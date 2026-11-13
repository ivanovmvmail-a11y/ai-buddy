"""HTTP API AI-buddy (Flask). Контракт — docs/API.md."""
import logging
import time
from typing import Literal

from flask import Flask, g, jsonify, request
from flask_cors import CORS
from pydantic import BaseModel, Field, ValidationError

from app import async_runner
from app.agent import analytics, explain, service
from app.agent import history as chat_history
from app.agent.actions import Action
from app.agent.users import get_user
from app.config import settings
from app.http_body import BadBody, json_body
from app.llm import Message
from app.onboarding_api import bp as onboarding_bp

USER_HEADER = "X-User-Id"
SCRIPTED_PROVIDERS = ("scenario", "echo")
log = logging.getLogger("ai_buddy.api")


MAX_MESSAGE_CHARS = 4000  # длиннее вопрос стажёра не бывает; защита от 200-КБ сообщений (аудит D8)
MAX_HISTORY = 40  # модели уходят последние 40 сообщений; более старые отбрасываются, а не ломают чат
MAX_HISTORY_ACCEPTED = 400  # защита от огромных запросов; длинная переписка обрезается, а не даёт 422 (проверка 13.11)


class ChatMessageIn(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    messages: list[ChatMessageIn] = Field(min_length=1, max_length=MAX_HISTORY_ACCEPTED)


class Source(BaseModel):
    title: str
    url: str | None = None


class ChatResponse(BaseModel):
    answer_id: str | None = None  # для оценки «полезно / не полезно» (спека 302)
    reply: str
    sources: list[Source] = []
    actions: list[Action] = []
    item_id: str | None = None  # пункт плана, о котором ответ (кнопки пункта в чате)
    mode: str | None = None  # "practice": следующее сообщение — ответ на задание


def _action_json(action: Action) -> dict:
    return action.model_dump(mode="json")


def configure_logging(level: str) -> None:
    """Журнал в stdout (Docker/Railway собирают его сами). Без этого INFO-строки агента терялись."""
    root = logging.getLogger()
    if not root.handlers:  # gunicorn/pytest могли уже настроить — не дублируем вывод
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))


def create_app() -> Flask:
    configure_logging(settings.log_level)
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = 512 * 1024
    app.json.ensure_ascii = False  # кириллица в ответах как есть, без \uXXXX

    origins = [o.strip() for o in settings.frontend_origins.split(",") if o.strip()]
    CORS(app, origins=origins, allow_headers=["Content-Type", USER_HEADER, "X-Demo-Key"])

    @app.before_request
    def load_user():
        # ИМИТАЦИЯ авторизации: в Авито пользователь берётся из корпоративного SSO.
        if request.endpoint in (None, "health") or request.method == "OPTIONS":
            return None
        user_id = request.headers.get(USER_HEADER)
        if not user_id:
            return jsonify(detail=f"Не указан пользователь: заголовок {USER_HEADER} (имитация входа, в Авито — SSO)"), 401
        user = get_user(user_id)
        if user is None:
            return jsonify(detail="Неизвестный пользователь"), 401
        g.user = user
        return None

    @app.errorhandler(BadBody)
    def bad_body(exc: BadBody):
        return jsonify(detail=str(exc)), 400

    # Ошибки самого Flask — тоже JSON, а не HTML-страница (аудит, мелочи)
    @app.errorhandler(404)
    def no_route(exc):
        return jsonify(detail="Нет такого адреса"), 404

    @app.errorhandler(405)
    def wrong_method(exc):
        return jsonify(detail="Этот метод здесь не поддерживается"), 405

    @app.errorhandler(413)
    def too_large(exc):
        return jsonify(detail="Слишком большой запрос"), 413

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
            req = ChatRequest.model_validate(json_body())
        except ValidationError as exc:
            return jsonify(detail=exc.errors(include_url=False, include_context=False, include_input=False)), 422
        last = req.messages[-1]
        if last.role != "user" or not last.content.strip():
            return jsonify(detail="Пустое сообщение"), 422

        # системные сообщения от клиента не принимаем — системный промпт задаёт только сервер
        history = [Message(role=m.role, content=m.content) for m in req.messages if m.role != "system"][-MAX_HISTORY:]
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
        try:
            async_runner.run(chat_history.record_turn(
                g.user.id, question, result.reply, sources=result.sources, answer_id=answer_id,
                scripted=settings.llm_provider in SCRIPTED_PROVIDERS))
        except Exception:  # история — удобство, ответ важнее
            log.exception("chat history not saved user=%s", g.user.id)
        return ChatResponse(
            answer_id=answer_id,
            reply=result.reply,
            sources=[Source(**s) for s in result.sources],
            actions=result.actions,
            item_id=result.item_id,
            mode=result.mode,
        ).model_dump(mode="json")

    @app.get("/chat/history")
    def get_chat_history():
        """Своя переписка, старые сверху (SPEC 9). Чужую историю получить нельзя: пользователь — из заголовка."""
        limit = min(request.args.get("limit", type=int) or chat_history.HISTORY_LIMIT, chat_history.HISTORY_LIMIT)
        items = async_runner.run(chat_history.history.list(g.user.id, limit))
        return {"messages": [e.model_dump(mode="json", exclude={"user_id"}) for e in items]}

    @app.get("/documents")
    def get_document():
        """Текст документа из «Источник» — только общий или своей команды (как поиск); чужой — 404."""
        title = (request.args.get("title") or "")[:200]
        doc = explain.view_document(title, g.user) if title.strip() else None
        if doc is None and title.startswith("Ответ наставника"):
            from app.onboarding_api import published_answer
            doc = async_runner.run(published_answer(title.strip(), g.user.team))
        if doc is None:
            return jsonify(detail="Документ не найден или недоступен"), 404
        return doc

    @app.get("/actions")
    def list_actions():
        return {"actions": [_action_json(a) for a in async_runner.run(service.agent.list_actions(g.user))]}

    @app.post("/actions/<action_id>/confirm")
    def confirm_action(action_id: str):
        return _action_json(async_runner.run(service.agent.confirm(g.user, action_id)))

    @app.post("/actions/<action_id>/cancel")
    def cancel_action(action_id: str):
        return _action_json(async_runner.run(service.agent.cancel(g.user, action_id)))

    app.register_blueprint(onboarding_bp)
    return app


app = create_app()
