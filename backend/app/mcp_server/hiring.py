"""Карта навыков: стажёр читает свою, изменяет только его наставник."""
from app.agent.users import DEMO_USERS, Role, User
from uuid import uuid4

from . import checklist, events, storage
from ._domain import known_actor, nonempty, require_intern, skill_level, strict_bool, timestamp, item_view
from .errors import Conflict, Forbidden, NotFound
from .models import SkillLevel, SkillProfile, SkillSuggestion, PlanItem


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


def _set_level(data, actor, profile, topic, level):
    intern_id = profile.intern_id
    if profile.skills.get(topic) != level:
        previous = profile.skills.get(topic)
        profile.skills[topic] = level
        profile.updated_by = actor.id
        profile.updated_at = timestamp(data, intern_id)
        checklist._rebuild_personal(data, actor, intern_id)
        events._record(data, actor, "skill_level_changed", {
            "intern_id": intern_id, "topic": topic, "from": previous, "to": level,
            "day": data.interns[intern_id].current_day,
        })


SUGGESTION_THRESHOLD = 2


def _maybe_suggest(data, intern_id, topic, *, known_item=None, closed_item=None):
    profile = data.profiles.get(intern_id)
    if profile is None or not topic:
        return
    level = profile.skills.get(topic)
    if level not in {"novice", "familiar"}:
        return
    target = DEMO_USERS[intern_id]
    mentor = DEMO_USERS.get(target.mentor_id)
    if mentor is None or mentor.role != Role.MENTOR or mentor.team != target.team:
        return
    closed = [item.id for item in data.items.values() if item.intern_id == intern_id
              and item.topic == topic and item.owner_role == "intern" and item.status == "done"]
    if known_item is None and len(closed) < SUGGESTION_THRESHOLD:
        return
    trigger = f"known:{known_item}" if known_item else f"done:{closed_item}"
    previous = [s for s in data.suggestions.values() if s.intern_id == intern_id and s.topic == topic]
    if any(trigger in s.evidence for s in previous):
        return
    evidence = [f"done:{id}" for id in sorted(closed)]
    if known_item:
        evidence.append(trigger)
    pending = next((s for s in previous if s.status == "pending"), None)
    if pending:
        pending.evidence = sorted(set(pending.evidence + evidence))
        return
    title = next((c.topic_title for c in data.personal_catalog.values()
                  if c.topic == topic and c.team == target.team), topic)
    suggestion = SkillSuggestion(id=f"SUG-{uuid4().hex}", intern_id=intern_id, mentor_id=mentor.id,
        topic=topic, from_level=level, to_level="familiar" if level == "novice" else "confident",
        basis='отмечено «это я уже знаю»' if known_item else f"закрыто {len(closed)} пункта по теме {title}",
        evidence=evidence, created_day=data.interns[intern_id].current_day)
    data.suggestions[suggestion.id] = suggestion
    events._record(data, target, "skill_suggestion_created", {
        "intern_id": intern_id, "suggestion_id": suggestion.id, "topic": topic,
    })


def _suggestion_view(data, suggestion):
    target = DEMO_USERS[suggestion.intern_id]
    title = next((c.topic_title for c in data.personal_catalog.values()
                  if c.topic == suggestion.topic and c.team == target.team), suggestion.topic)
    return suggestion.model_copy(update={"intern_name": target.name, "topic_title": title}, deep=True)


async def list_suggestions(actor: User, intern_id: str | None = None, status: str | None = "pending") -> list[SkillSuggestion]:
    known_actor(actor)
    if actor.role != Role.MENTOR:
        raise NotFound()
    async with storage.get_store().read() as data:
        if intern_id is not None:
            require_intern(data, actor, intern_id, private=True)
        if status is not None:
            from typing import Literal
            from pydantic import TypeAdapter
            status = TypeAdapter(Literal["pending", "accepted", "dismissed"]).validate_python(status)
        return [_suggestion_view(data, s) for s in reversed(list(data.suggestions.values()))
                if s.mentor_id == actor.id and DEMO_USERS[s.intern_id].mentor_id == actor.id
                and (intern_id is None or s.intern_id == intern_id) and (status is None or s.status == status)]


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
            _set_level(data, actor, profile, suggestion.topic, suggestion.to_level)
        suggestion.status = "accepted" if accept else "dismissed"
        suggestion.decided_day = data.interns[suggestion.intern_id].current_day
        events._record(data, actor, "skill_suggestion_decided", {
            "intern_id": suggestion.intern_id, "suggestion_id": suggestion.id,
            "topic": suggestion.topic, "status": suggestion.status,
        })
        return _suggestion_view(data, suggestion)


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
