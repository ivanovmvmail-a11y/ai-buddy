"""План, следующий шаг, лестница и фактическая сводка недели."""
from app.agent.users import Role, User
from pydantic import TypeAdapter

from . import events, storage
from ._domain import STAGES, WORK_STAGES, item_view, nonempty, owner_id, positive, require_intern, timestamp
from .errors import Conflict, Forbidden, NotFound
from .models import ItemStatus, NextStep, OnboardingData, Plan, PlanItem, StageInfo


def _change_status(data: OnboardingData, actor: User, item: PlanItem, status: ItemStatus,
                  reason: str | None = None, waiting_for: str | None = None):
    old = item.status
    item.status = status
    item.status_reason = reason
    item.waiting_for = waiting_for if status == "waiting" else None
    item.waiting_days = 0 if status == "waiting" else None
    item.updated_at = timestamp(data, item.intern_id)
    item.updated_by = actor.id
    events._record(data, actor, "plan_item_status_changed", {
        "intern_id": item.intern_id, "item_id": item.id, "title": item.title,
        "from": old, "to": status, "reason": reason, "day": data.interns[item.intern_id].current_day,
    })
    if status == "done":
        for reminder in data.reminders.values():
            if reminder.plan_item_id == item.id and reminder.status != "done":
                reminder.status = "done"
                reminder.snooze_until_day = None
                events._record(data, actor, "reminder_completed", {"intern_id": item.intern_id, "reminder_id": reminder.id})


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
    async with storage.get_store().transaction() as data:
        require_intern(data, actor, intern_id)
        plan = _build_plan(data, actor, intern_id)
        events._record(data, actor, "plan_viewed", {"intern_id": intern_id})
        events._record(data, actor, "next_step_shown", {"intern_id": intern_id,
                      "item_id": plan.next_step.item.id if plan.next_step.item else None})
        return plan


async def set_item_status(actor: User, item_id: str, status: ItemStatus, reason: str | None = None) -> PlanItem:
    async with storage.get_store().transaction() as data:
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
        status = TypeAdapter(ItemStatus).validate_python(status)
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
    async with storage.get_store().transaction() as data:
        require_intern(data, actor, intern_id)
        week = positive.validate_python(week)
        start, end = (week - 1) * 7 + 1, week * 7
        facts = [event for event in data.events if event.payload.get("intern_id") == intern_id
                 and start <= event.payload.get("day", 0) <= end]
        closed = {event.payload["item_id"]: event.payload for event in facts
                  if event.type == "plan_item_status_changed" and event.payload.get("to") == "done"}
        granted = {event.payload["request_id"]: event.payload for event in facts
                   if event.type == "access_request_decided" and event.payload.get("status") == "granted"}
        carry = [item_view(data, item) for item in data.items.values() if item.intern_id == intern_id
                 and item.stage in WORK_STAGES and item.status != "done"
                 and (item.stage == "week1" or week >= 2)]
        return {"intern_id": intern_id, "week": week, "closed": list(closed.values()),
                "access_granted": list(granted.values()), "carry_over": carry}
