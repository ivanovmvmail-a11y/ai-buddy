"""Демо-часы и однократные напоминания; отправок сообщений нет."""
from uuid import uuid4

from app.agent.users import DEMO_USERS, User

from . import events, storage
from ._domain import WORK_STAGES, intern, known_actor, owner_id, positive
from ._system import require_system
from .errors import Conflict, NotFound
from .models import OnboardingData, Reminder


def _tick(data: OnboardingData, actor: User, day: int | None = None, intern_ids: set[str] | None = None) -> list[Reminder]:
    created = []
    for item in data.items.values():
        if item.stage not in WORK_STAGES or (intern_ids is not None and item.intern_id not in intern_ids):
            continue
        current_day = day if day is not None else data.interns[item.intern_id].current_day
        existing = next((reminder for reminder in data.reminders.values() if reminder.plan_item_id == item.id), None)
        if existing:
            if item.status == "done" and existing.status != "done":
                existing.status, existing.snooze_until_day = "done", None
                events._record(data, actor, "reminder_completed", {"intern_id": item.intern_id, "reminder_id": existing.id})
            elif existing.status == "snoozed" and current_day >= existing.snooze_until_day:
                existing.status, existing.snooze_until_day = "active", None
                events._record(data, actor, "reminder_reactivated", {"intern_id": item.intern_id, "reminder_id": existing.id})
            continue
        if item.status == "done":
            continue
        pending = next((request for request in data.requests.values()
                        if request.plan_item_id == item.id and request.status == "pending_approval"
                        and current_day - request.created_day >= 2), None)
        overdue = item.due_day is not None and current_day > item.due_day
        if not pending and not overdue:
            continue
        if pending:
            approver = DEMO_USERS[pending.approver_id].name
            text = f"Заявка {pending.id} ждёт {approver}. Напомнить наставнику?"
        else:
            text = f"У пункта «{item.title}» прошёл срок. Можно вернуться к нему или обсудить препятствие."
        reminder = Reminder(id=f"REM-{uuid4().hex}", user_id=item.intern_id if pending else owner_id(item),
                            plan_item_id=item.id, request_id=pending.id if pending else None,
                            text=text, created_day=current_day)
        data.reminders[reminder.id] = reminder
        created.append(reminder)
        events._record(data, actor, "reminder_created", {"intern_id": item.intern_id, "reminder_id": reminder.id,
                      "item_id": item.id, "day": current_day})
    return created


async def get_day(actor: User, intern_id: str) -> int:
    known_actor(actor)
    async with storage.get_store().transaction() as data:
        intern(data, intern_id)
        return data.interns[intern_id].current_day


async def advance_day(actor: User, intern_id: str | None = None) -> dict[str, int]:
    known_actor(actor)
    async with storage.get_store().transaction() as data:
        targets = [intern_id] if intern_id is not None else list(data.interns)
        for target in targets:
            intern(data, target)
        result = {}
        for target in targets:
            state = data.interns[target]
            state.current_day += 1
            result[target] = state.current_day
            events._record(data, actor, "day_advanced", {"intern_id": target, "day": state.current_day})
        _tick(data, actor, intern_ids=set(targets))
        return result


async def cron_tick(actor: User, day: int | None = None) -> list[Reminder]:
    known_actor(actor)
    require_system()
    if day is not None:
        day = positive.validate_python(day)
    async with storage.get_store().transaction() as data:
        return _tick(data, actor, day)


async def list_reminders(actor: User) -> list[Reminder]:
    known_actor(actor)
    async with storage.get_store().transaction() as data:
        return [reminder for reminder in data.reminders.values() if reminder.user_id == actor.id]


async def snooze_reminder(actor: User, id: str, days: int = 1) -> Reminder:
    known_actor(actor)
    async with storage.get_store().transaction() as data:
        reminder = data.reminders.get(id)
        if reminder is None or reminder.user_id != actor.id:
            raise NotFound()
        days = positive.validate_python(days)
        if reminder.status == "done":
            raise Conflict()
        item = data.items.get(reminder.plan_item_id)
        current = data.interns[item.intern_id].current_day if item else max(state.current_day for state in data.interns.values())
        reminder.status, reminder.snooze_until_day = "snoozed", current + days
        events._record(data, actor, "reminder_snoozed", {"reminder_id": id, "days": days})
        return reminder


async def done_reminder(actor: User, id: str) -> Reminder:
    known_actor(actor)
    async with storage.get_store().transaction() as data:
        reminder = data.reminders.get(id)
        if reminder is None or reminder.user_id != actor.id:
            raise NotFound()
        if reminder.status != "done":
            reminder.status, reminder.snooze_until_day = "done", None
            events._record(data, actor, "reminder_completed", {"reminder_id": id})
        return reminder


async def reset_demo(actor: User) -> None:
    from .seed import reset_demo as reset
    await reset(actor)
