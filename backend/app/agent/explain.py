"""Объяснение пункта плана без модели (аудит S1, S7; спека 102).

Раньше без ключа интерфейс собирал один шаблон на все пункты, а подсказки «по шагам» и «к кому идти»
уходили в чат без пункта — поиск находил чужой абзац. Теперь сервер берёт раздел документа, привязанного
к пункту, и строит ответ под уровень стажёра. Ничего не выдумывает: шаги — это предложения документа,
люди — из оргструктуры демо-пользователей, практика — из пункта плана.

При внедрении документ берётся из базы знаний (Confluence) по doc_source_id; здесь — демо-документы.
"""
import re
from dataclasses import dataclass
from functools import cache
from typing import Literal
from urllib.parse import urlparse

from app.llm.scenario_provider import _overlap, _units, _words
from app.mcp_server import checklist, hiring
from app.mcp_server.errors import NotFound
from app.rag.ingest import DEMO_DOCS, read_document

from .users import DEMO_USERS, Role, User

Kind = Literal["explain", "steps", "who"]
KINDS: tuple[Kind, ...] = ("explain", "steps", "who")
CHIPS = {"steps": "Как это сделать по шагам?", "who": "К кому идти, если не получается?"}
# Публичный репозиторий: у демо-документа рабочая ссылка на его текст (у вымышленных адресов example.invalid её нет).
DEMO_DOCS_URL = "https://github.com/ivanovmvmail-a11y/ai-buddy/blob/main/backend/app/rag/demo_docs/"
WHO_DOC = "demo:04-who-to-ask.md"
OWNER_RU = {"mentor": "наставник", "lead": "руководитель", "curator": "куратор", "hrbp": "HR BP"}


@dataclass(frozen=True)
class Doc:
    source_id: str
    title: str
    url: str | None
    sections: tuple[tuple[str, str], ...]  # (заголовок раздела, абзац)


@cache
def load_doc(source_id: str | None) -> Doc | None:
    if not source_id or not source_id.startswith("demo:"):
        return None
    path = DEMO_DOCS / source_id.removeprefix("demo:")
    if path.parent != DEMO_DOCS or not path.is_file():
        return None
    doc = read_document(path, source_id)
    url = doc.url if doc.url and urlparse(doc.url).hostname not in (None, "example.invalid") else DEMO_DOCS_URL + path.name
    return Doc(source_id, doc.title, url, tuple(_units(doc.content)))


def _best_section(doc: Doc, text: str) -> tuple[str, list[str]]:
    """Раздел документа, ближе всего к пункту: (заголовок, абзацы раздела)."""
    by_heading: dict[str, list[str]] = {}
    for heading, unit in doc.sections:
        by_heading.setdefault(heading, []).append(unit)
    wanted = _words(text)
    heading = max(by_heading, key=lambda h: (_overlap(wanted, h + " " + " ".join(by_heading[h])), -list(by_heading).index(h)))
    return heading, by_heading[heading]


def _sentences(paragraphs: list[str]) -> list[str]:
    out = []
    for p in paragraphs:
        out.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"^([-*]|\d+\.)\s+", "", p)) if s.strip())
    return out


def _person(user_id: str | None, fallback: str) -> str:
    user = DEMO_USERS.get(user_id or "")
    return user.name if user else fallback


def _team_person(team: str, role: Role) -> str | None:
    return next((u.name for u in DEMO_USERS.values() if u.role == role and u.team == team), None) or next(
        (u.name for u in DEMO_USERS.values() if u.role == role), None)


def _owner(item, intern) -> str:
    if item.owner_role == "mentor":
        return _person(intern.mentor_id if intern else None, "наставник")
    role = {"lead": Role.LEAD, "curator": Role.CURATOR, "hrbp": Role.HRBP}.get(item.owner_role)
    return (_team_person(intern.team if intern else "", role) if role else None) or OWNER_RU.get(item.owner_role, item.owner_role)


async def explain_item(actor: User, intern_id: str, item_id: str, kind: Kind) -> dict:
    """{"title", "text", "source": {"title","url"} | None, "chips": [...], "with_source": bool}. Чужой пункт — NotFound."""
    plan = await checklist.get_plan(actor, intern_id)
    item = next((i for i in plan.items if i.id == item_id), None)
    if item is None:
        raise NotFound()
    level = None
    if item.topic:
        try:
            level = (await hiring.get_skill_profile(actor, intern_id)).skills.get(item.topic)
        except Exception:  # профиль не обязателен: нет доступа или нет профиля — объясняем без уровня
            level = None
    doc = load_doc(item.doc_source_id)
    intern = DEMO_USERS.get(intern_id)
    builder = {"explain": _explain, "steps": _steps, "who": _who}[kind]
    text, used = builder(item, doc, level, intern)
    source = {"title": used.title, "url": used.url} if used else None
    return {"title": item.title, "text": text, "source": source, "with_source": source is not None,
            "chips": [CHIPS[k] for k in ("steps", "who") if k != kind]}


def _explain(item, doc, level, intern):
    parts = [f"«{item.title}» — {item.summary}"]
    if doc:
        heading, paragraphs = _best_section(doc, f"{item.title} {item.summary} {item.practice or ''}")
        sentences = _sentences(paragraphs)
        if level == "confident":
            parts.append(f"Эту тему ты знаешь уверенно, поэтому коротко. Главное из раздела «{heading}»: {sentences[0]}")
        elif level == "familiar":
            parts.append(f"Коротко по разделу «{heading}»: " + " ".join(sentences[:2]))
        else:
            intro = "Разберём подробно, с примерами." if level == "novice" else ""
            parts.append((intro + "\n\n" if intro else "") + f"Из раздела «{heading}»:\n" + "\n".join(paragraphs))
    elif item.owner_role != "intern":
        parts.append(f"Этот пункт отмечает {OWNER_RU.get(item.owner_role, item.owner_role)} — {_owner(item, intern)}. "
                     "От тебя — договориться о времени и прийти с вопросами.")
    if item.practice:
        parts.append(f"Задание на практике: {item.practice}")
    return "\n\n".join(parts), doc


def _steps(item, doc, level, intern):
    if not doc:
        mentor = _person(intern.mentor_id if intern else None, "наставник")
        return (f"Пошаговой инструкции к «{item.title}» в документах нет — выдумывать не буду. Короткий путь: "
                f"{item.summary} Если неясно, с чего начать, спроси {mentor}."
                + (f"\n\nЗадание на практике: {item.practice}" if item.practice else "")), None
    heading, paragraphs = _best_section(doc, f"{item.title} {item.summary} {item.practice or ''}")
    steps = _sentences(paragraphs)
    lines = [f"По шагам — по разделу «{heading}» документа «{doc.title}»:"]
    lines += [f"{n}. {s}" for n, s in enumerate(steps, 1)]
    if item.practice:
        lines.append(f"{len(steps) + 1}. Проверь себя на практике: {item.practice}")
    lines.append("Если застрял больше чем на 30 минут — спроси наставника, вопрос помогу сформулировать.")
    return "\n".join(lines), doc


def _who(item, doc, level, intern):
    mentor = _person(intern.mentor_id if intern else None, "наставник")
    lines = []
    if item.status == "waiting" and item.waiting_for:
        lines.append(f"Сейчас пункт ждёт: {_person(item.waiting_for, 'согласующий')}. Если ответа нет больше дня — "
                     "напиши ему коротко, со ссылкой на заявку.")
    if item.owner_role != "intern":
        lines.append(f"Этот пункт ведёт {OWNER_RU.get(item.owner_role, item.owner_role)} — {_owner(item, intern)}.")
    lines.append(f"По содержанию задачи и если что-то не получается — твой наставник, {mentor}.")
    who_doc = load_doc(WHO_DOC)
    if who_doc:
        topic_words = "доступ ресурс ошибка" if item.resource_id else f"{item.title} {item.summary}"
        heading, paragraphs = _best_section(who_doc, topic_words)
        lines.append(f"Из документа «{who_doc.title}», раздел «{heading}»: " + " ".join(paragraphs))
    return "\n\n".join(lines), who_doc
