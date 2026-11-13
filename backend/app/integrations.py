"""Точки подключения для систем Авито (внедряемость, чекпоинт 2, 13.11).

Эксперт: «вы стартап, мы хотим вас забрать — что сделать, чтобы перетянуть проект, не переписывая код? Может, у вас есть
доступы на внешку». Здесь — входы для систем, а не для людей:

- `POST /integrations/hired` — система найма присылает карту навыков стажёра по итогам собеседования; бот сам
  пересобирает персональную часть плана и сообщает стажёру. Учётка стажёра — из корпоративного каталога (SSO).
  Ключ службы: `Authorization: Bearer INTEGRATION_TOKEN`.
- `POST /integrations/mattermost` — исходящий вебхук или slash-команда Mattermost: сообщение из мессенджера отвечает тот
  же агент, с теми же правами и черновиками. Mattermost подписывает запрос своим токеном (`MATTERMOST_TOKEN`).

Пустой ключ — вход выключен (503): на публичном стенде без настройки никто не сможет им воспользоваться.
"""
import hmac
import logging

from flask import Blueprint, jsonify, request
from pydantic import BaseModel, Field, ValidationError

from app import async_runner
from app.agent import history as chat_history
from app.agent import service
from app.agent.users import DEMO_USERS, Role, get_user
from app.config import settings
from app.llm import Message
from app.mcp_server import hiring
from app.mcp_server.errors import NotFound

bp = Blueprint("integrations", __name__, url_prefix="/integrations")
log = logging.getLogger("ai_buddy.integrations")


def _same(given: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(given.encode(), expected.encode())


def _off(name: str):
    return jsonify(detail=f"Интеграция выключена: задайте {name} в backend/.env"), 503


class HiredIn(BaseModel):
    """Итоги собеседования из системы найма."""
    intern_id: str = Field(description="id стажёра в корпоративном каталоге, например intern-liza")
    skills: dict[str, str] = Field(description="Уровень по темам: novice | familiar | confident, например {\"git\": \"novice\"}")
    strengths: list[str] | None = Field(default=None, description="Сильные стороны (видит стажёр и наставник)")
    growth: list[str] | None = Field(default=None, description="Темы для роста")


@bp.post("/hired")
def integration_hired():
    """Стажёр нанят: карта навыков из системы найма → персональный план.

    Общие пункты плана не меняются; персональные пересобираются по карте навыков (новичок по теме → практикум).
    Стажёр получает уведомление «План обновлён по итогам собеседования». Ключ службы — INTEGRATION_TOKEN."""
    if not settings.integration_token:
        return _off("INTEGRATION_TOKEN")
    token = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not _same(token, settings.integration_token):
        return jsonify(detail="Неверный ключ службы"), 401
    try:
        body = HiredIn.model_validate(request.get_json(silent=True) or {})
    except ValidationError as exc:
        return jsonify(detail=exc.errors(include_url=False, include_context=False, include_input=False)), 422
    user = DEMO_USERS.get(body.intern_id)
    if user is None or user.role != Role.INTERN:
        return jsonify(detail="Стажёр не найден в каталоге"), 404
    try:
        result = async_runner.run(hiring.apply_hiring_profile(body.intern_id, body.skills, body.strengths, body.growth))
    except NotFound:
        return jsonify(detail="Стажёр не найден в каталоге"), 404
    except ValidationError:
        return jsonify(detail="Уровень по теме — novice, familiar или confident"), 422
    log.info("hiring profile applied intern=%s added=%d removed=%d", body.intern_id, len(result["added"]), len(result["removed"]))
    return result


# Пользователь Mattermost → пользователь AI-buddy. В Авито — один корпоративный каталог (SSO), здесь — таблица соответствия:
# MATTERMOST_USERS="anya.smirnova=intern-anya,petr.volkov=mentor-petr"; без неё логин Mattermost совпадает с id в демо.
def _mm_user(username: str):
    mapping = dict(pair.split("=", 1) for pair in settings.mattermost_users.split(",") if "=" in pair)
    return get_user(mapping.get(username.strip(), username.strip()))


@bp.post("/mattermost")
def integration_mattermost():
    """Сообщение из Mattermost (исходящий вебхук или slash-команда) → ответ агента в канал.

    Mattermost шлёт форму или JSON с полями token, user_name, text, trigger_word. Ответ — тот же агент, что в веб-чате:
    те же права, документы и черновики (подтверждение черновика — в AI-buddy). Ответ виден только автору."""
    if not settings.mattermost_token:
        return _off("MATTERMOST_TOKEN")
    payload = request.get_json(silent=True) or request.form.to_dict()
    if not _same(str(payload.get("token", "")), settings.mattermost_token):
        return jsonify(detail="Неверный токен Mattermost"), 401
    user = _mm_user(str(payload.get("user_name", "")))
    if user is None:
        return {"response_type": "ephemeral", "text": "Не нашёл тебя в каталоге AI-buddy — напиши наставнику."}
    text = str(payload.get("text", "")).strip()
    trigger = str(payload.get("trigger_word", "")).strip()
    if trigger and text.lower().startswith(trigger.lower()):
        text = text[len(trigger):].strip()
    if not text:
        return {"response_type": "ephemeral", "text": "Напиши вопрос после команды, например: «что мне делать дальше?»"}
    past = async_runner.run(chat_history.history.list(user.id, 20))
    messages = [Message(role=e.role, content=e.content) for e in past if e.role in ("user", "assistant")][-19:]
    messages.append(Message(role="user", content=text[:4000]))
    try:
        result = async_runner.run(service.agent.answer(messages, user))
    except Exception:
        log.exception("mattermost answer failed user=%s", user.id)
        return {"response_type": "ephemeral", "text": "Помощник временно недоступен. Попробуй через минуту."}
    reply = result.reply
    if result.sources:
        reply += "\n\nИсточник: " + ", ".join(s["title"] for s in result.sources)
    if result.actions:
        reply += "\n\n📝 Черновик ждёт подтверждения в AI-buddy — без него ничего не отправится."
    try:
        async_runner.run(chat_history.record_turn(user.id, text, result.reply, sources=result.sources))
    except Exception:  # история — удобство
        log.exception("mattermost history not saved user=%s", user.id)
    return {"response_type": "ephemeral", "username": "AI-buddy", "text": reply}
