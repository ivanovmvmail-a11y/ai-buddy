"""Карта навыков: стажёр читает свою, изменяет только его наставник."""
from pydantic import TypeAdapter

from app.agent.users import Role, User

from . import events, storage
from ._domain import nonempty, require_intern, timestamp
from .errors import Forbidden, NotFound
from .models import SkillLevel, SkillProfile


async def get_skill_profile(actor: User, intern_id: str) -> SkillProfile:
    async with storage.get_store().transaction() as data:
        require_intern(data, actor, intern_id, private=True)
        if intern_id not in data.profiles:
            raise NotFound()
        return data.profiles[intern_id]


async def set_skill_level(actor: User, intern_id: str, topic: str, level: SkillLevel) -> SkillProfile:
    async with storage.get_store().transaction() as data:
        require_intern(data, actor, intern_id, private=True)
        if actor.role != Role.MENTOR:
            raise Forbidden()
        profile = data.profiles.get(intern_id)
        if profile is None:
            raise NotFound()
        topic = nonempty.validate_python(topic)
        level = TypeAdapter(SkillLevel).validate_python(level)
        if profile.skills.get(topic) != level:
            previous = profile.skills.get(topic)
            profile.skills[topic] = level
            profile.updated_by = actor.id
            profile.updated_at = timestamp(data, intern_id)
            events._record(data, actor, "skill_level_changed", {
                "intern_id": intern_id, "topic": topic, "from": previous, "to": level,
                "day": data.interns[intern_id].current_day,
            })
        return profile
