"""План, следующий шаг, лестница и фактическая сводка недели."""
from copy import deepcopy
from uuid import uuid4
from app.agent.users import DEMO_USERS, Role, User

from . import events, storage
from .notifications import notify
from ._domain import STAGES, WORK_STAGES, item_status, item_view, nonempty, owner_id, positive, require_intern, timestamp
from ._system import SYSTEM_ACTOR
from .errors import Conflict, Forbidden, NotFound
from .models import ItemStatus, NextStep, OnboardingData, Plan, PlanItem, StageInfo, CatalogItem


def _change_status(data: OnboardingData, actor: User, item: PlanItem, status: ItemStatus,
                  reason: str | None = None, waiting_for: str | None = None, *, day: int | None = None):
    day = data.interns[item.intern_id].current_day if day is None else positive.validate_python(day)
    old = item.status
    item.status = status
    item.status_reason = reason
    item.waiting_for = waiting_for if status == "waiting" else None
    item.waiting_days = 0 if status == "waiting" else None
    item.updated_at = timestamp(data, item.intern_id, day)
    item.updated_by = actor.id
    events._record(data, actor, "plan_item_status_changed", {
        "intern_id": item.intern_id, "item_id": item.id, "title": item.title,
        "from": old, "to": status, "reason": reason, "day": day, "waiting_for": item.waiting_for,
    })
    if status == "done":
        for reminder in data.reminders.values():
            if reminder.plan_item_id == item.id and reminder.status != "done":
                reminder.status = "done"
                reminder.snooze_until_day = None
                events._record(data, SYSTEM_ACTOR, "reminder_completed", {
                    "intern_id": item.intern_id, "reminder_id": reminder.id, "day": day,
                })

    if status == "done" and old != "done":
        from .hiring import _maybe_suggest
        _maybe_suggest(data, item.intern_id, item.topic, closed_item=item.id)


def _build_plan(data: OnboardingData, actor: User, intern_id: str) -> Plan:
    items = sorted((item_view(data, item) for item in data.items.values() if item.intern_id == intern_id),
                   key=lambda item: (STAGES.index(item.stage), item.order, item.id))
    ladder = []
    current_found = False
    for stages, title in [(WORK_STAGES, "Недели 1–2"), (("month1",), "Месяц 1"),
                          (("month2",), "Месяц 2"), (("after3m",), "После 3 месяцев")]:
        group = [item for item in items if item.stage in stages]
        done = sum(item.status == "done" for item in group)
        passed = bool(group) and done == len(group)
        state = "passed" if passed else ("ahead" if current_found else "current")
        if not passed:
            current_found = True
        ladder.append(StageInfo(stage=stages[0], title=title, total=len(group), done=done, state=state))
    candidates = [item for item in items if item.stage in WORK_STAGES and item.owner_role == actor.role
                  and item.status not in {"done", "waiting"}]
    candidates.sort(key=lambda item: (not item.overdue, STAGES.index(item.stage), item.order, item.id))
    waiting = [item for item in items if item.stage in WORK_STAGES and item.status == "waiting"]
    return Plan(intern_id=intern_id, current_day=data.interns[intern_id].current_day, items=items,
                ladder=ladder, next_step=NextStep(item=candidates[0] if candidates else None, waiting=waiting))


async def get_plan(actor: User, intern_id: str) -> Plan:
    async with storage.get_store().read() as data:
        require_intern(data, actor, intern_id)
        plan = _build_plan(data, actor, intern_id)
        events._record(data, actor, "plan_viewed", {"intern_id": intern_id})
        events._record(data, actor, "next_step_shown", {"intern_id": intern_id,
                      "item_id": plan.next_step.item.id if plan.next_step.item else None})
        return plan


async def set_item_status(actor: User, item_id: str, status: ItemStatus, reason: str | None = None) -> PlanItem:
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        item = data.items.get(item_id)
        if item is None:
            raise NotFound()
        target = require_intern(data, actor, item.intern_id)
        if item.stage not in WORK_STAGES or item.resource_id:
            raise Forbidden("Пункт с сервисом или этап-контур нельзя менять вручную")
        is_owner = actor.id == owner_id(item) and actor.role == item.owner_role
        returning = actor.role == Role.MENTOR and target.mentor_id == actor.id and item.owner_role == "intern"
        if not is_owner and not returning:
            raise Forbidden()
        status = item_status.validate_python(status)
        if returning and not is_owner:
            if item.status != "done" or status != "in_progress":
                raise Conflict()
            reason = nonempty.validate_python(reason)
        elif status != item.status and (status == "not_started" or (item.status == "done" and status != "in_progress")):
            raise Conflict()
        if status != item.status:
            waiting_for = target.mentor_id if actor.role == Role.INTERN else target.id
            _change_status(data, actor, item, status, reason, waiting_for)
        return item_view(data, item)


async def weekly_summary(actor: User, intern_id: str, week: int) -> dict:
    async with storage.get_store().read(include_events=True) as data:
        require_intern(data, actor, intern_id)
        week = positive.validate_python(week)
        start, end = (week - 1) * 7 + 1, week * 7
        cutoff = min(end, data.interns[intern_id].current_day)
        facts = [event for event in data.events if event.payload.get("intern_id") == intern_id
                 and event.payload.get("day", 0) <= cutoff]
        # Сортируем по виртуальному дню; внутри дня порядок событий задаёт журнал.
        # Seed может добавлять исторические события не в календарном порядке.
        facts.sort(key=lambda event: event.payload.get("day", 0))
        last = {event.payload["item_id"]: event for event in facts
                if event.type == "plan_item_status_changed"}
        closed, carry = [], []
        for item in data.items.values():
            if item.intern_id != intern_id or item.stage not in WORK_STAGES or (item.stage == "week2" and week < 2):
                continue
            event = last.get(item.id)
            historical = item.model_copy(update={
                "status": event.payload["to"] if event else "not_started",
                "status_reason": event.payload.get("reason") if event else None,
                "waiting_for": event.payload.get("waiting_for") if event else None,
                "updated_at": timestamp(data, intern_id, event.payload["day"] if event else 1),
                "updated_by": event.user_id if event else None,
            }, deep=True)
            if historical.status != "done":
                carry.append(item_view(data, historical, cutoff))
            elif event is not None and start <= event.payload["day"]:
                closed.append(deepcopy(event.payload))
        granted = {event.payload["request_id"]: deepcopy(event.payload) for event in facts
                   if event.type == "access_request_decided" and event.payload.get("status") == "granted"
                   and start <= event.payload["day"]}
        return {"intern_id": intern_id, "week": week, "closed": closed,
                "access_granted": list(granted.values()), "carry_over": carry}


def _remove_personal(data, actor, item):
    # История напоминаний сохраняется, FK на снятый пункт больше не нужен.
    for reminder in data.reminders.values():
        if reminder.plan_item_id == item.id:
            reminder.plan_item_id = None
            reminder.status, reminder.snooze_until_day = "done", None
    del data.items[item.id]
    events._record(data, actor, "personal_item_removed", {
        "intern_id": item.intern_id, "item_id": item.id, "topic": item.topic,
    })


def _add_personal(data, actor, intern_id, entry, *, reason=None):
    item = PlanItem(id=f"{intern_id.removeprefix('intern-')}.p.{entry.topic}", intern_id=intern_id,
        kind="personal", reason=reason or f"в карте навыков {entry.topic_title} — новичок",
        catalog_key=entry.key, topic=entry.topic, title=entry.title, summary=entry.summary,
        doc_source_id=entry.doc_source_id, practice=entry.practice, stage=entry.stage,
        order=100, owner_role="intern", due_day=entry.due_offset,
        updated_at=timestamp(data, intern_id), updated_by=actor.id)
    data.items[item.id] = item
    events._record(data, actor, "personal_item_added", {
        "intern_id": intern_id, "item_id": item.id, "topic": entry.topic, "catalog_key": entry.key,
    })
    # Явный каталог (#71) передаёт reason; пересборка использует причину из карты.
    if reason is not None and actor.role == Role.MENTOR:
        notify(data, intern_id, intern_id, "personal_item_added", uuid4().hex,
               f"В план добавлен пункт для тебя: {item.title} ({item.reason})",
               "plan_item", plan_item_id=item.id)
    return item


def _rebuild_personal(data, actor, intern_id):
    profile = data.profiles[intern_id]
    for item in list(data.items.values()):
        if (item.intern_id == intern_id and item.kind == "personal" and item.status != "done"
                and profile.skills.get(item.topic) != "novice"):
            _remove_personal(data, actor, item)
    user = DEMO_USERS[intern_id]
    for entry in data.personal_catalog.values():
        if (entry.team == user.team and profile.skills.get(entry.topic) == entry.level
                and not any(item.intern_id == intern_id and item.catalog_key == entry.key for item in data.items.values())):
            _add_personal(data, actor, intern_id, entry)


async def list_catalog(actor: User, intern_id: str) -> list[CatalogItem]:
    async with storage.get_store().read() as data:
        user = require_intern(data, actor, intern_id, private=True)
        if actor.role != Role.MENTOR:
            raise NotFound()
        keys = {item.catalog_key for item in data.items.values() if item.intern_id == intern_id}
        return [entry.model_copy(update={"in_plan": entry.key in keys}, deep=True)
                for entry in data.personal_catalog.values() if entry.team == user.team]
