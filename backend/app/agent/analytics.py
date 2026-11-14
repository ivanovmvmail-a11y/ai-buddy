"""События чата и метрики пользы (спека 302).

Пишем только тему вопроса и флаги ответа — НЕ текст вопроса и не текст ответа: метрики показывают
наставнику, где стажёрам не хватает документов, а не следят за конкретным человеком.
События лежат в общем журнале имитаций сервисов (`app.mcp_server.events`, таблица `events`) от имени
системы; кто спрашивал — в payload.
"""
import logging
import re
import uuid
from collections import Counter

from app.mcp_server import events
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import NotFound

from .users import DEMO_USERS, Role, User, can_view_intern

log = logging.getLogger("ai_buddy.analytics")

# Порядок важен: первая подходящая тема. Ключи — начала слов, регистр не важен.
TOPICS: list[tuple[str, tuple[str, ...]]] = [
    # Проверка 14.11: больше половины вопросов попадало в «другое» (удалёнка, CI, «что мне осталось», «кто отвечает
    # за…») — панель наставника выглядела пустой. Ключи дополнены; порядок прежний.
    ("hr", ("отпуск", "больнич", "отгул", "зарплат", "зп", "аванс", "оклад", "компенсац", "справк", "дмс",
            "удален", "удалён", "из дома", "офис", "столов", "обед", "пропуск")),
    ("access", ("доступ", "заявк", "права", "пароль")),
    ("git", ("git", "гит", "репозитор", "pull", "пулл", "ревью", "review", "ветк", "коммит", "мерж", "bitbucket",
             "запулить", "код")),
    ("environment", ("стенд", "песочниц", "запуст", "пайплайн", "pipeline", "ноутбук", "окружени", "vpn", "сборк",
                     "ci", "тест", "деплой", "проект", "оборудован")),
    ("tasks", ("задач", "бэклог", "jira", "джир", "спринт", "тикет", "приорит", "готов")),
    ("plan", ("план", "дальше", "следующ", "чек-лист", "чеклист", "прогресс", "срок", "осталось", "успева",
              "практикум", "задани", "экватор", "стажировк", "цел", "что мне делать", "что делать")),
    ("people", ("кого", "к кому", "наставник", "встреч", "1:1", "руководител", "команд", "кто ", "кто?", "куратор",
                "коллег")),
]
TOPIC_TITLES = {
    "hr": "орг. вопросы (HR)", "access": "доступы", "git": "git и ревью", "environment": "окружение и запуск",
    "tasks": "задачи", "plan": "план", "people": "к кому идти", "other": "другое",
}
NOT_FOUND = ("этого нет", "не нашёл", "не нашел", "нет информации", "нет данных")
CONFLICT = "документы расходятся"  # SPEC 3.7: и модель, и сценарный режим пишут эту фразу при противоречии
REFUSED = ("нет доступа", "не могу показать", "недоступ", "не раскрыва", "данные другого стажёра")


def topic_of(question: str) -> str:
    q = question.lower()
    for topic, keys in TOPICS:
        if any(re.search(rf"(?<![а-яa-z]){re.escape(k)}", q) for k in keys):
            return topic
    return "other"


def new_answer_id() -> str:
    return f"ans_{uuid.uuid4().hex[:12]}"


def _who(user: User) -> dict:
    who = {"user_id": user.id, "role": user.role.value, "team": user.team}
    if user.role == Role.INTERN:
        who["intern_id"] = user.id
    return who


async def record_answer(user: User, *, answer_id: str, question: str, reply: str, sources: int,
                        tools: list[str], refused: bool, drafts: int, latency_ms: int) -> None:
    low = reply.lower()
    payload = {
        **_who(user), "answer_id": answer_id, "topic": topic_of(question), "with_source": sources > 0,
        "refused": refused or any(w in low for w in REFUSED), "not_in_base": any(w in low for w in NOT_FOUND), "conflict": CONFLICT in low,
        "tools": tools, "drafts": drafts, "latency_ms": latency_ms,
    }
    try:
        await events.log_event(SYSTEM_ACTOR, "question_answered", payload)
    except Exception:  # аналитика не должна ломать чат
        log.exception("question_answered not recorded user=%s", user.id)


async def record_explained(user: User, *, answer_id: str, title: str, with_source: bool, latency_ms: int) -> None:
    """Сценарный режим: объяснение пункта собрано из данных плана без модели — событие как у /chat."""
    await record_answer(user, answer_id=answer_id, question=title, reply="", sources=int(with_source),
                        tools=["explain_item"], refused=False, drafts=0, latency_ms=latency_ms)


async def record_practice(user: User, *, item_id: str, topic: str | None, passed: bool) -> None:
    """Спека 107: задание на практике сдано — засчитано или нет. Без текста ответа."""
    try:
        await events.log_event(SYSTEM_ACTOR, "practice_checked",
                               {**_who(user), "item_id": item_id, "topic": topic, "passed": passed})
    except Exception:  # аналитика не должна ломать проверку
        log.exception("practice_checked not recorded user=%s", user.id)


async def record_feedback(user: User, answer_id: str, useful: bool) -> None:
    answered = await events.list_events(SYSTEM_ACTOR, type="question_answered")
    if not any(e.payload.get("answer_id") == answer_id and e.payload.get("user_id") == user.id for e in answered):
        raise NotFound()  # чужой или несуществующий ответ неразличимы
    await events.log_event(SYSTEM_ACTOR, "answer_feedback", {**_who(user), "answer_id": answer_id, "useful": useful})


def visible_interns(viewer: User) -> list[str]:
    if viewer.role not in (Role.MENTOR, Role.LEAD, Role.CURATOR):
        return []
    return [u.id for u in DEMO_USERS.values() if u.role == Role.INTERN and can_view_intern(viewer, u)]


def closed_without_human(p: dict) -> bool:
    """Вопрос закрыт без человека: ответ по документу или по данным сервиса, без отказа и без «нет в базе»."""
    if p.get("refused") or p.get("not_in_base") or p.get("conflict") or p.get("topic") == "hr":
        return False
    return bool(p.get("with_source") or p.get("tools"))


async def metrics(viewer: User, intern_id: str | None = None) -> dict:
    scope = visible_interns(viewer)
    if intern_id is not None:
        if intern_id not in scope:
            raise NotFound()
        scope = [intern_id]
    if not scope:
        raise NotFound()
    all_events = await events.list_events(SYSTEM_ACTOR)
    answers = [e.payload for e in all_events if e.type == "question_answered" and e.payload.get("intern_id") in scope]
    feedback = [e.payload for e in all_events if e.type == "answer_feedback" and e.payload.get("intern_id") in scope]
    n = len(answers)
    topics = Counter(p["topic"] for p in answers)
    gaps = Counter(p["topic"] for p in answers if p.get("not_in_base"))
    conflicts = Counter(p["topic"] for p in answers if p.get("conflict"))
    useful = sum(1 for p in feedback if p.get("useful"))
    return {
        "interns": scope,
        "questions": n,
        "closed_without_human": sum(closed_without_human(p) for p in answers),
        "with_source_share": round(sum(bool(p.get("with_source")) for p in answers) / n, 2) if n else 0.0,
        "refused": sum(bool(p.get("refused")) for p in answers),
        "drafts": sum(int(p.get("drafts") or 0) for p in answers),
        "avg_latency_ms": round(sum(int(p.get("latency_ms") or 0) for p in answers) / n) if n else 0,
        "feedback": {"useful": useful, "not_useful": len(feedback) - useful},
        "topics": [{"topic": t, "title": TOPIC_TITLES[t], "count": c} for t, c in topics.most_common()],
        "unanswered_topics": [{"topic": t, "title": TOPIC_TITLES[t], "count": c} for t, c in gaps.most_common()],
        # Документы противоречат друг другу (SPEC 3.7) — сигнал наставнику обновить документ.
        "conflict_topics": [{"topic": t, "title": TOPIC_TITLES[t], "count": c} for t, c in conflicts.most_common()],
    }
