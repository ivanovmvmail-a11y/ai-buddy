"""Демо-часы и однократные напоминания; отправок сообщений нет."""
import re
from datetime import date
from uuid import uuid4

from app.agent.users import DEMO_USERS, Role, User

from . import events, storage
from ._domain import WORK_STAGES, intern, known_actor, owner_id, positive
from ._system import SYSTEM_ACTOR, require_system
from .errors import Conflict, Forbidden, NotFound
from .models import Actor, OnboardingData, Reminder


def _tick(data: OnboardingData, day: int | None = None, intern_ids: set[str] | None = None) -> list[Reminder]:
    created = []
    for item in data.items.values():
        if item.stage not in WORK_STAGES or (intern_ids is not None and item.intern_id not in intern_ids):
            continue
        current_day = day if day is not None else data.interns[item.intern_id].current_day
        existing = next((reminder for reminder in data.reminders.values() if reminder.plan_item_id == item.id and reminder.kind in {"plan_item", "access_request"}), None)
        if existing:
            if item.status == "done" and existing.status != "done":
                existing.status, existing.snooze_until_day = "done", None
                events._record(data, SYSTEM_ACTOR, "reminder_completed", {
                    "intern_id": item.intern_id, "reminder_id": existing.id, "day": current_day,
                })
            elif existing.status == "snoozed" and current_day >= existing.snooze_until_day:
                existing.status, existing.snooze_until_day = "active", None
                events._record(data, SYSTEM_ACTOR, "reminder_reactivated", {
                    "intern_id": item.intern_id, "reminder_id": existing.id, "day": current_day,
                })
            continue
        if item.status == "done":
            continue
        pending = next((request for request in data.requests.values()
                        if request.plan_item_id == item.id and request.status == "pending_approval"), None)
        waiting_request = item.status == "waiting" and pending is not None
        ready = pending is not None and current_day - pending.created_day >= 2
        overdue = not waiting_request and item.due_day is not None and current_day > item.due_day
        if not ready and not overdue:
            continue
        if ready:
            approver = DEMO_USERS[pending.approver_id].name
            text = f"Заявка {pending.id} ждёт решения наставника ({approver}). Напомнить наставнику?"
        else:
            text = f"У пункта «{item.title}» прошёл срок. Можно вернуться к нему или обсудить препятствие."
        reminder = Reminder(id=f"REM-{uuid4().hex}", user_id=item.intern_id if ready else owner_id(item),
                            plan_item_id=item.id, request_id=pending.id if ready else None,
                            kind="access_request" if ready else "plan_item",
                            action={"label": "Открыть", "target": "access_request" if ready else "plan_item"},
                            intern_id=item.intern_id, text=text, created_day=current_day)
        data.reminders[reminder.id] = reminder
        created.append(reminder)
        events._record(data, SYSTEM_ACTOR, "reminder_created", {"intern_id": item.intern_id, "reminder_id": reminder.id,
                      "item_id": item.id, "day": current_day})
    from .absence import _tick_absences
    from .mentor_inbox import tick_questions
    created.extend(tick_questions(data, day, intern_ids))
    created.extend(_tick_absences(data, day, intern_ids))
    for reminder in data.reminders.values():
        if reminder.kind in {"plan_item", "access_request"} or reminder.status != "snoozed":
            continue
        state = data.interns.get(reminder.intern_id)
        if state is None or (intern_ids is not None and state.intern_id not in intern_ids):
            continue
        current = day if day is not None else state.current_day
        if current >= reminder.snooze_until_day:
            reminder.status, reminder.snooze_until_day = "active", None
    return [reminder.model_copy(deep=True) for reminder in created]


async def get_day(actor: User, intern_id: str) -> int:
    known_actor(actor)
    async with storage.get_store().read() as data:
        intern(data, intern_id)
        return data.interns[intern_id].current_day


async def advance_day(actor: User, intern_id: str | None = None) -> dict[str, int]:
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        targets = [intern_id] if intern_id is not None else list(data.interns)
        for target in targets:
            intern(data, target)
        result = {}
        for target in targets:
            state = data.interns[target]
            state.current_day += 1
            result[target] = state.current_day
            events._record(data, actor, "day_advanced", {"intern_id": target, "day": state.current_day})
        _tick(data, intern_ids=set(targets))
        return result


async def cron_tick(actor: Actor, day: int | None = None) -> list[Reminder]:
    require_system(actor)
    if day is not None:
        day = positive.validate_python(day)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        return _tick(data, day)


async def list_reminders(actor: User, *, include_mentor: bool = False) -> list[Reminder]:
    known_actor(actor)
    async with storage.get_store().read() as data:
        return [reminder.model_copy(deep=True) for reminder in data.reminders.values() if reminder.user_id == actor.id
                and (include_mentor or reminder.mentor_question_id is None)]


def _custom_text(text: str, female: bool = False) -> str:
    # «напомни про 1:1» → «Ты просил(а)» → по роду: «Ты просила напомнить про 1:1»; «напомни оформить пропуск» → «…: оформить пропуск».
    asked = "Ты просила" if female else "Ты просил"
    if re.match(r"(?:что|чтобы)\s", text, re.IGNORECASE):
        return f"{asked} напомнить, {text}"
    if re.match(r"(?:про|о|об|насч[её]т)\s", text, re.IGNORECASE):
        return f"{asked} напомнить {text}"
    return f"{asked} напомнить: {text}"


CUSTOM_MAX_DAYS = 60  # дальше двух месяцев — это уже календарь, а не напоминание стажировки


async def add_custom_reminder(actor: User, text: str, day: date) -> Reminder:
    """Напоминание по просьбе стажёра («напомни в пятницу про 1:1»): только себе, на дату не раньше сегодняшней.
    До нужного дня лежит отложенным и всплывает в колокольчике, когда демо-часы до него дойдут (общий цикл
    `_tick` возвращает отложенные). Отложить/готово — как у остальных. Claude, 13.11 (HANDOFF 13.11 п. 2)."""
    known_actor(actor)
    if actor.role != Role.INTERN:
        raise Forbidden()
    text = re.sub(r"\s+", " ", text).strip()
    if not text or len(text) > 300:
        raise Conflict("Текст напоминания — от 1 до 300 символов")
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        intern(data, actor.id)
        state = data.interns[actor.id]
        target = (day - state.start_date).days + 1
        if target < state.current_day:
            raise Conflict("Эта дата уже прошла")
        if target - state.current_day > CUSTOM_MAX_DAYS:
            raise Conflict("Напоминание можно поставить не дальше чем на два месяца вперёд")
        later = target > state.current_day
        reminder = Reminder(id=f"REM-{uuid4().hex}", user_id=actor.id, intern_id=actor.id, kind="custom",
                            action={"label": "Открыть", "target": "plan"}, text=_custom_text(text, getattr(actor, "female", False)),
                            created_day=state.current_day, status="snoozed" if later else "active",
                            snooze_until_day=target if later else None)
        data.reminders[reminder.id] = reminder
        events._record(data, actor, "reminder_created", {"intern_id": actor.id, "reminder_id": reminder.id,
                                                          "kind": "custom", "remind_day": target})
        return reminder.model_copy(deep=True)


def _reminder_context(data: OnboardingData, reminder: Reminder) -> dict:
    if reminder.mentor_question_id:
        question = data.mentor_questions[reminder.mentor_question_id]
        return {"kind": "mentor_question", "day": data.interns[question.intern_id].current_day}
    item = data.items.get(reminder.plan_item_id)
    request = data.requests.get(reminder.request_id)
    intern_id = reminder.intern_id or (item.intern_id if item else (request.intern_id if request else reminder.user_id))
    state = data.interns.get(intern_id)
    # Все напоминания плана имеют стажёра; для несвязанного личного напоминания
    # сотрудника не подставляем id чужого стажёра.
    return {"intern_id": intern_id if state else None,
            "day": state.current_day if state else max(state.current_day for state in data.interns.values())}


async def snooze_reminder(actor: User, id: str, days: int = 1) -> Reminder:
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        reminder = data.reminders.get(id)
        if reminder is None or reminder.user_id != actor.id:
            raise NotFound()
        days = positive.validate_python(days)
        if reminder.status == "done":
            raise Conflict()
        context = _reminder_context(data, reminder)
        reminder.status, reminder.snooze_until_day = "snoozed", context["day"] + days
        events._record(data, actor, "reminder_snoozed", {"reminder_id": id, "days": days, **context})
        return reminder.model_copy(deep=True)


async def done_reminder(actor: User, id: str) -> Reminder:
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        reminder = data.reminders.get(id)
        if reminder is None or reminder.user_id != actor.id:
            raise NotFound()
        if reminder.status != "done":
            reminder.status, reminder.snooze_until_day = "done", None
            events._record(data, actor, "reminder_completed", {"reminder_id": id, **_reminder_context(data, reminder)})
        return reminder.model_copy(deep=True)


async def reset_demo(actor: User) -> None:
    from .seed import reset_demo as reset
    await reset(actor)
