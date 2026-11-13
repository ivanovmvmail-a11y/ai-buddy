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
from typing import Any, Literal
from urllib.parse import urlparse

from app.llm.scenario_provider import _overlap, _units, _words
from app.mcp_server import checklist, hiring
from app.mcp_server.errors import NotFound
from app.rag.ingest import DEMO_DOCS, read_document

from .users import DEMO_USERS, Role, User, name_in

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


@cache
def _by_title() -> dict[str, tuple[str | None, str]]:
    """Название демо-документа → (команда или None для общих, текст без служебного заголовка)."""
    found: dict[str, tuple[str | None, str]] = {}
    for path in sorted(DEMO_DOCS.glob("*.md")):
        doc = read_document(path, f"demo:{path.name}")
        found[doc.title] = (doc.team, doc.content)
    return found


def view_document(title: str, user: User) -> dict | None:
    """Документ целиком по названию из «Источник» (проверка 12.11: ссылки вели на несуществующий адрес).
    Правило то же, что у поиска: общий документ или документ своей команды; чужой — как будто его нет.
    При внедрении — ссылка на страницу базы знаний (Confluence) с её правами."""
    found = _by_title().get(title.strip())
    if found is None:
        return None
    team, content = found
    if team is not None and team != user.team:
        return None
    return {"title": title.strip(), "team": team, "content": content}


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


def _owner_user(item, intern) -> User | None:
    if item.owner_role == "mentor":
        return DEMO_USERS.get(intern.mentor_id or "") if intern else None
    if item.owner_role == "lead" and intern and intern.lead_id:
        return DEMO_USERS.get(intern.lead_id)
    role = {"lead": Role.LEAD, "curator": Role.CURATOR, "hrbp": Role.HRBP}.get(item.owner_role)
    team = intern.team if intern else ""
    return next((u for u in DEMO_USERS.values() if u.role == role and u.team == team), None) or next(
        (u for u in DEMO_USERS.values() if u.role == role), None)


def _owner(item, intern) -> str:
    owner = _owner_user(item, intern)
    return owner.name if owner else OWNER_RU.get(item.owner_role, item.owner_role)


@dataclass(frozen=True)
class View:
    """Кто смотрит на пункт (проверка 13.11: наставник нажал «Объяснить» у своего пункта и прочитал
    «Этот пункт отмечает наставник — Пётр Волков. От тебя — договориться о времени…»)."""
    item: Any
    doc: Doc | None
    level: str | None
    intern: User | None
    actor: User

    @property
    def is_intern(self) -> bool:
        return self.intern is not None and self.actor.id == self.intern.id

    @property
    def is_owner(self) -> bool:
        owner = _owner_user(self.item, self.intern)
        return self.item.owner_role != "intern" and owner is not None and owner.id == self.actor.id


def _clean(text: str) -> str:
    """Служебная пометка «демо-данные, не регламент Авито.» — для интерфейса, не для текста ответа."""
    text = re.sub(r"^\s*демо-данные, не регламент Авито\.?\s*", "", text or "", flags=re.IGNORECASE).strip()
    return text[:1].upper() + text[1:]


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text[1:2].islower() else text


MEETING_WORDS = ("встреч", "1:1", "обсуд", "цел")


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
    view = View(item, load_doc(item.doc_source_id), level, DEMO_USERS.get(intern_id), actor)
    builder = {"explain": _explain, "steps": _steps, "who": _who}[kind]
    text, used = builder(view)
    source = {"title": used.title, "url": used.url} if used else None
    # «К кому идти, если не получается?» — вопрос стажёра; наставнику и руководителю он не нужен.
    chips = [CHIPS[k] for k in ("steps", "who") if k != kind and (k != "who" or view.is_intern)]
    return {"title": item.title, "text": text, "source": source, "with_source": source is not None, "chips": chips}


def _doc_part(view: View) -> str:
    item, doc, level = view.item, view.doc, view.level
    heading, paragraphs = _best_section(doc, f"{item.title} {item.summary} {item.practice or ''}")
    sentences = _sentences(paragraphs)
    if not view.is_intern:  # уровень — подсказка глубины для самого стажёра, другим — раздел целиком
        return f"Из раздела «{heading}»:\n" + "\n".join(paragraphs)
    if level == "confident" and sentences:
        return f"Эту тему ты знаешь уверенно, поэтому коротко. Главное из раздела «{heading}»: {sentences[0]}"
    if level == "familiar":
        return f"Коротко по разделу «{heading}»: " + " ".join(sentences[:2])
    intro = "Разберём подробно, с примерами." if level == "novice" else ""
    return (intro + "\n\n" if intro else "") + f"Из раздела «{heading}»:\n" + "\n".join(paragraphs)


def _explain(view: View):
    item, intern = view.item, view.intern
    summary = _clean(item.summary)
    owner_role = OWNER_RU.get(item.owner_role, item.owner_role)
    owner = _owner_user(item, intern)
    who = f"{owner_role} — {owner.name}" if owner else owner_role
    parts: list[str] = []
    if item.owner_role == "intern":
        if view.is_intern:
            parts.append(f"«{item.title}». {summary}")
        else:
            parts.append(f"«{item.title}» — пункт {name_in(intern, 'gen', 'стажёра')}. "
                         f"Что сделать стажёру: {_lower_first(summary)}")
    elif view.is_owner:
        parts.append(f"«{item.title}» — твой пункт. {summary}")
    elif view.is_intern:
        if any(w in item.title.lower() for w in MEETING_WORDS):
            parts.append(f"«{item.title}» — этот пункт отмечает {who}. От тебя — договориться о времени и прийти "
                         "с вопросами.")
        else:
            nudge = f"напомни {name_in(owner, 'dat')}" if owner else "напомни ответственному"
            parts.append(f"«{item.title}» — это делает {who}, тебе ничего делать не нужно. Если срок прошёл, а пункт "
                         f"не закрыт, {nudge}.")
    else:
        parts.append(f"«{item.title}» — пункт ведёт {who}. {summary}")
    if view.doc:
        parts.append(_doc_part(view))
    if item.practice:
        label = ("Задание на практике (вместе со стажёром)" if view.is_owner
                 else "Задание на практике (вместе)" if item.owner_role != "intern" else "Задание на практике")
        parts.append(f"{label}: {item.practice}")
    if view.is_owner and item.status != "done":
        parts.append("Когда сделаешь — нажми «Готово» у пункта в плане.")
    return "\n\n".join(parts), view.doc


def _steps(view: View):
    item, doc, intern = view.item, view.doc, view.intern
    mentor = DEMO_USERS.get(intern.mentor_id or "") if intern else None
    if not doc:
        ask = ""
        if view.is_intern:
            ask = (f" Если неясно, с чего начать, спроси наставника — {mentor.name}." if mentor
                   else " Если неясно, с чего начать, спроси наставника.")
        return (f"Пошаговой инструкции к «{item.title}» в документах нет — выдумывать не буду. Короткий путь: "
                f"{_clean(item.summary)}{ask}"
                + (f"\n\nЗадание на практике: {item.practice}" if item.practice else "")), None
    heading, paragraphs = _best_section(doc, f"{item.title} {item.summary} {item.practice or ''}")
    steps = _sentences(paragraphs)
    lines = [f"По шагам — по разделу «{heading}» документа «{doc.title}»:"]
    lines += [f"{n}. {s}" for n, s in enumerate(steps, 1)]
    if item.practice:
        lines.append(f"{len(steps) + 1}. Проверь себя на практике: {item.practice}" if view.is_intern
                     else f"{len(steps) + 1}. Задание на практике: {item.practice}")
    if view.is_intern:
        lines.append("Если застрял больше чем на 30 минут — спроси наставника, вопрос помогу сформулировать.")
    return "\n".join(lines), doc


def _who(view: View):
    item, intern = view.item, view.intern
    mentor = DEMO_USERS.get(intern.mentor_id or "") if intern else None
    lines = []
    if item.status == "waiting" and item.waiting_for:
        waiting = DEMO_USERS.get(item.waiting_for)
        lines.append(f"Сейчас пункт ждёт: {waiting.name if waiting else 'согласующий'}. Если ответа нет больше дня — "
                     f"напиши {name_in(waiting, 'dat', 'согласующему')} коротко, со ссылкой на заявку.")
    if item.owner_role != "intern":
        lines.append(f"Этот пункт ведёт {OWNER_RU.get(item.owner_role, item.owner_role)} — {_owner(item, intern)}.")
    if view.is_intern:
        lines.append(f"По содержанию задачи и если что-то не получается — твой наставник, {mentor.name}." if mentor
                     else "По содержанию задачи и если что-то не получается — твой наставник.")
    elif mentor and view.actor.id == mentor.id:
        lines.append("По содержанию задачи стажёру помогаешь ты.")
    elif mentor:
        lines.append(f"По содержанию задачи стажёру помогает наставник — {mentor.name}.")
    who_doc = load_doc(WHO_DOC) if view.is_intern else None
    if who_doc:
        topic_words = "доступ ресурс ошибка" if item.resource_id else f"{item.title} {item.summary}"
        heading, paragraphs = _best_section(who_doc, topic_words)
        lines.append(f"Из документа «{who_doc.title}», раздел «{heading}»: " + " ".join(paragraphs))
    return "\n\n".join(lines), who_doc
