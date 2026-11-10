"""Внутренний Clickstream-подобный журнал: бизнес-actor хранится вместе с событием."""
from datetime import datetime, timezone

from . import storage
from ._domain import nonempty, timestamp
from ._system import require_system
from .models import Actor, Event, OnboardingData


def _record(data: OnboardingData, actor: Actor, type: str, payload: dict) -> Event:
    """Только из уже авторизованной бизнес-транзакции, не пользовательский инструмент."""
    intern_id = payload.get("intern_id")
    event = Event(
        ts=timestamp(data, intern_id, payload.get("day")) if intern_id in data.interns else datetime.now(timezone.utc),
        user_id=actor.id, role=actor.role, team=actor.team, type=type, payload=payload,
    )
    data.events.append(event)
    return event


async def log_event(actor: Actor, type: str, payload: dict) -> Event:
    require_system(actor)
    type = nonempty.validate_python(type)
    async with storage.get_store().transaction() as data:
        return _record(data, actor, type, payload)


async def list_events(actor: Actor, intern_id: str | None = None, type: str | None = None) -> list[Event]:
    require_system(actor)
    async with storage.get_store().transaction() as data:
        return [event for event in data.events
                if (intern_id is None or event.payload.get("intern_id") == intern_id)
                and (type is None or event.type == type)]
