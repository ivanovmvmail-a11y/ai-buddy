"""Карта навыков: стажёр читает свою, изменяет только его наставник."""
from app.agent.users import DEMO_USERS, Role, User
from uuid import uuid4

from . import checklist, events, storage
from .notifications import notify
from ._domain import SKILL_LEVEL_LABELS, SKILL_LEVEL_ORDER, known_actor, nonempty, require_intern, skill_level, strict_bool, timestamp, item_view, suggestion_status
from .errors import Conflict, Forbidden, NotFound
from .models import SkillLevel, SkillProfile, SkillSuggestion, PlanItem
from ._system import SYSTEM_ACTOR


async def get_skill_profile(actor: User, intern_id: str) -> SkillProfile:
    async with storage.get_store().read() as data:
        require_intern(data, actor, intern_id, private=True)
        if intern_id not in data.profiles:
            raise NotFound()
        return data.profiles[intern_id].model_copy(deep=True)


async def set_skill_level(actor: User, intern_id: str, topic: str, level: SkillLevel) -> SkillProfile:
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        require_intern(data, actor, intern_id, private=True)
        if actor.role != Role.MENTOR:
            raise Forbidden()
        profile = data.profiles.get(intern_id)
        if profile is None:
            raise NotFound()
        topic = nonempty.validate_python(topic)
        level = skill_level.validate_python(level)
        _set_level(data, actor, profile, topic, level)
        return profile.model_copy(deep=True)


def _set_level(data, actor, profile, topic, level, *, accepted_suggestion_id=None):
    intern_id = profile.intern_id
    if profile.skills.get(topic) != level:
        previous = profile.skills.get(topic)
        for suggestion in data.suggestions.values():
            if (suggestion.intern_id == intern_id and suggestion.topic == topic
                    and suggestion.status == "pending" and suggestion.id != accepted_suggestion_id):
                suggestion.status = "dismissed"
                suggestion.decided_day = data.interns[intern_id].current_day
                for reminder in data.reminders.values():
                    if reminder.suggestion_id == suggestion.id:
                        reminder.status, reminder.snooze_until_day = "done", None
                events._record(data, actor, "skill_suggestion_decided", {
                    "intern_id": intern_id, "suggestion_id": suggestion.id, "topic": topic,
                    "status": "dismissed", "cause": "manual_skill_change",
                })
        profile.skills[topic] = level
        profile.updated_by = actor.id
        profile.updated_at = timestamp(data, intern_id)
        checklist._rebuild_personal(data, actor, intern_id, topic=topic)
        events._record(data, actor, "skill_level_changed", {
            "intern_id": intern_id, "topic": topic, "from": previous, "to": level,
            "day": data.interns[intern_id].current_day,
        })
        target = DEMO_USERS.get(intern_id)
        if target is not None:
            title = _topic_title(data, topic, target.team)
            # Один актуальный факт по теме; snooze не должен оживить старый уровень.
            for reminder in data.reminders.values():
                if (reminder.user_id == intern_id and reminder.kind == "skill_changed"
                        and reminder.action is not None and reminder.action.topic == topic
                        and reminder.status != "done"):
                    reminder.status, reminder.snooze_until_day = "done", None
            promotion = level != "novice" and (previous is None
                or SKILL_LEVEL_ORDER.index(level) > SKILL_LEVEL_ORDER.index(previous))
            text = (f"Наставник отметил: {title} — {SKILL_LEVEL_LABELS[level]}. План обновился" if promotion
                    else f"План по теме {title} обновился. Открой актуальные пункты")
            notify(data, intern_id, intern_id, "skill_changed", uuid4().hex, text, "plan", topic=topic)


SUGGESTION_THRESHOLD = 2


def _maybe_suggest(data, intern_id, topic, *, known_item=None, closed_item=None, practice_item=None, practice_basis=None):
    profile = data.profiles.get(intern_id)
    if not data._suggestions_available or profile is None or not topic:
        return
    level = profile.skills.get(topic)
    if level not in {"novice", "familiar"}:
        return
    target = DEMO_USERS.get(intern_id)
    if target is None or target.role != Role.INTERN:
        return
    mentor = DEMO_USERS.get(target.mentor_id)
    if mentor is None or mentor.role != Role.MENTOR or mentor.team != target.team:
        return
    closed = [item.id for item in data.items.values() if item.intern_id == intern_id
              and item.topic == topic and item.owner_role == "intern" and item.status == "done"]
    if known_item is None and practice_item is None and len(closed) < SUGGESTION_THRESHOLD:
        return
    trigger = (f"known:{known_item}" if known_item else
               f"practice:{practice_item}" if practice_item else f"done:{closed_item}")
    previous = [s for s in data.suggestions.values() if s.intern_id == intern_id and s.topic == topic]
    if any(trigger in s.evidence for s in previous):
        return
    evidence = [f"done:{id}" for id in sorted(closed)]
    if known_item or practice_item:
        evidence.append(trigger)
    pending = next((s for s in previous if s.status == "pending"), None)
    if pending:
        pending.evidence = sorted(set(pending.evidence + evidence))
        return
    title = _topic_title(data, topic, target.team)
    suggestion = SkillSuggestion(id=f"SUG-{uuid4().hex}", intern_id=intern_id, mentor_id=mentor.id,
        topic=topic, from_level=level, to_level="familiar" if level == "novice" else "confident",
        basis=('отмечено «это я уже знаю»' if known_item else practice_basis if practice_item
               else _closed_basis(len(closed), title)),
        evidence=evidence, created_day=data.interns[intern_id].current_day)
    data.suggestions[suggestion.id] = suggestion
    events._record(data, SYSTEM_ACTOR, "skill_suggestion_created", {
        "intern_id": intern_id, "suggestion_id": suggestion.id, "topic": topic,
    })
    notify(data, mentor.id, intern_id, "skill_suggestion", suggestion.id,
           f"Бот предлагает поднять уровень: {target.name}, {title} ({suggestion.basis})",
           "skill_suggestion", suggestion_id=suggestion.id)


def _topic_title(data, topic, team):
    return next((c.topic_title for c in data.personal_catalog.values()
                 if c.topic == topic and c.team == team), topic)


def _closed_basis(count, title):
    if count % 10 == 1 and count % 100 != 11:
        phrase = f"закрыт {count} пункт"
    elif 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        phrase = f"закрыто {count} пункта"
    else:
        phrase = f"закрыто {count} пунктов"
    return f"{phrase} по теме {title}"


def _suggestion_view(data, suggestion):
    target = DEMO_USERS.get(suggestion.intern_id)
    if target is None or target.role != Role.INTERN:
        return None
    return suggestion.model_copy(update={"intern_name": target.name,
        "topic_title": _topic_title(data, suggestion.topic, target.team)}, deep=True)


async def list_suggestions(actor: User, intern_id: str | None = None, status: str | None = "pending") -> list[SkillSuggestion]:
    known_actor(actor)
    if actor.role != Role.MENTOR:
        raise NotFound()
    async with storage.get_store().read() as data:
        if intern_id is not None:
            require_intern(data, actor, intern_id, private=True)
        if status is not None:
            status = suggestion_status.validate_python(status)
        result = []
        for suggestion in reversed(list(data.suggestions.values())):
            if (suggestion.mentor_id != actor.id or (intern_id is not None and suggestion.intern_id != intern_id)
                    or (status is not None and suggestion.status != status)):
                continue
            target = DEMO_USERS.get(suggestion.intern_id)
            if target is None or target.mentor_id != actor.id:
                continue
            view = _suggestion_view(data, suggestion)
            if view is not None:
                result.append(view)
        return result


async def decide_suggestion(actor: User, suggestion_id: str, accept: bool) -> SkillSuggestion:
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        suggestion = data.suggestions.get(suggestion_id)
        if suggestion is None or actor.role != Role.MENTOR or suggestion.mentor_id != actor.id:
            raise NotFound()
        require_intern(data, actor, suggestion.intern_id, private=True)
        accept = strict_bool.validate_python(accept)
        if suggestion.status != "pending":
            raise Conflict("Предложение уже рассмотрено")
        profile = data.profiles.get(suggestion.intern_id)
        if profile is None:
            raise NotFound()
        if accept:
            if profile.skills.get(suggestion.topic) != suggestion.from_level:
                raise Conflict("Уровень уже изменён; оставьте предложение без изменения")
            _set_level(data, actor, profile, suggestion.topic, suggestion.to_level,
                       accepted_suggestion_id=suggestion.id)
        suggestion.status = "accepted" if accept else "dismissed"
        suggestion.decided_day = data.interns[suggestion.intern_id].current_day
        for reminder in data.reminders.values():
            if reminder.suggestion_id == suggestion.id:
                reminder.status, reminder.snooze_until_day = "done", None
        events._record(data, actor, "skill_suggestion_decided", {
            "intern_id": suggestion.intern_id, "suggestion_id": suggestion.id,
            "topic": suggestion.topic, "status": suggestion.status,
        })
        view = _suggestion_view(data, suggestion)
        if view is None:
            raise NotFound()
        return view


async def mark_known(actor: User, item_id: str, known: bool = True) -> PlanItem:
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        item = data.items.get(item_id)
        if item is None or actor.role != Role.INTERN or item.intern_id != actor.id or item.owner_role != "intern":
            raise NotFound()
        require_intern(data, actor, item.intern_id, private=True)
        nonempty.validate_python(item.topic)
        known = strict_bool.validate_python(known)
        if item.known_marked != known:
            item.known_marked = known
            events._record(data, actor, "plan_item_known_marked", {
                "intern_id": item.intern_id, "item_id": item.id, "known": known,
            })
            if known:
                _maybe_suggest(data, item.intern_id, item.topic, known_item=item.id)
        return item_view(data, item)


async def note_practice_passed(actor: User, item_id: str, found: list[str]) -> None:
    """Стажёр сдал практическое задание пункта (спека 107, проверка 13.11): наставник видит это основанием
    предложения поднять уровень — что именно засчитано. Уровень по-прежнему меняет только наставник."""
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        item = data.items.get(item_id)
        if item is None or actor.role != Role.INTERN or item.intern_id != actor.id or item.owner_role != "intern":
            raise NotFound()
        require_intern(data, actor, item.intern_id, private=True)
        if not item.topic:
            return
        events._record(data, actor, "practice_passed", {"intern_id": item.intern_id, "item_id": item.id})
        basis = "сдано практическое задание" + (": " + ", ".join(found) if found else "")
        _maybe_suggest(data, item.intern_id, item.topic, practice_item=item.id, practice_basis=basis[:200])


async def apply_hiring_profile(intern_id: str, skills: dict[str, SkillLevel], strengths: list[str] | None = None,
                               growth: list[str] | None = None) -> dict:
    """Карта навыков из системы найма (внедряемость, чекпоинт 2; Claude 13.11): учётка стажёра уже есть в корпоративном
    каталоге, найм присылает итоги собеседования — бот пересобирает персональную часть плана (общие пункты не трогает,
    ручные пункты наставника и закрытые — тоже) и сообщает стажёру. Вызывает служба (SYSTEM_ACTOR), не человек."""
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        profile = data.profiles.get(intern_id)
        if profile is None or intern_id not in data.interns:
            raise NotFound()
        levels = {nonempty.validate_python(topic): skill_level.validate_python(level) for topic, level in skills.items()}

        def personal() -> dict[str, str]:
            return {item.id: item.title for item in data.items.values()
                    if item.intern_id == intern_id and item.kind == "personal" and item.status != "done"}

        before = personal()
        profile.skills = {**profile.skills, **levels}
        if strengths is not None:
            profile.strengths = list(strengths)
        if growth is not None:
            profile.growth = list(growth)
        profile.updated_by = "hiring"
        profile.updated_at = timestamp(data, intern_id)
        checklist._rebuild_personal(data, SYSTEM_ACTOR, intern_id)
        after = personal()
        added = [after[i] for i in after if i not in before]
        removed = [before[i] for i in before if i not in after]
        events._record(data, SYSTEM_ACTOR, "hiring_profile_received", {
            "intern_id": intern_id, "topics": sorted(levels), "added": len(added), "removed": len(removed)})
        if added or removed:
            parts = ([f"добавлено: {', '.join(added)}"] if added else []) + ([f"убрано: {', '.join(removed)}"] if removed else [])
            notify(data, intern_id, intern_id, "skill_changed", uuid4().hex,
                   "План обновлён по итогам собеседования — " + "; ".join(parts), "plan")
        return {"intern_id": intern_id, "skills": dict(profile.skills), "added": added, "removed": removed,
                "personal": list(after.values())}
