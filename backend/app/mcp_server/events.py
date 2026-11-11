"""Внутренний Clickstream-подобный журнал: бизнес-actor хранится вместе с событием."""
from datetime import datetime, timezone

from . import storage
from ._domain import nonempty
from ._system import require_system
from .models import Actor, Event, OnboardingData


def _record(data: OnboardingData, actor: Actor, type: str, payload: dict) -> Event:
    """Только из уже авторизованной бизнес-транзакции, не пользовательский инструмент."""
    intern_id = payload.get("intern_id", actor.id)
    if intern_id in data.interns:
        payload = {**payload}
        payload.setdefault("day", data.interns[intern_id].current_day)
    event = Event(
        ts=datetime.now(timezone.utc),
        user_id=actor.id, role=actor.role, team=actor.team, type=type, payload=payload,
    )
    data.events.append(event)
    return event


async def log_event(actor: Actor, type: str, payload: dict) -> Event:
    require_system(actor)
    type = nonempty.validate_python(type)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        return _record(data, actor, type, payload).model_copy(deep=True)


async def list_events(actor: Actor, intern_id: str | None = None, type: str | None = None) -> list[Event]:
    require_system(actor)
    async with storage.get_store().read(include_events=True) as data:
        return [event.model_copy(deep=True) for event in data.events
                if (intern_id is None or event.payload.get("intern_id") == intern_id)
                and (type is None or event.type == type)]
