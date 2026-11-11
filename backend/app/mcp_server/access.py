"""Имитация выдачи доступов: автоматическая либо с решением наставника."""
from app.agent.users import DEMO_USERS, Role, User

from . import checklist, events, storage
from ._domain import access_level, can_read_private, intern, known_actor, nonempty, strict_bool, timestamp
from ._system import SYSTEM_ACTOR
from .errors import Conflict, Forbidden, NotFound
from .models import AccessLevel, AccessRequest, AccessResource


async def list_resources(actor: User) -> list[AccessResource]:
    known_actor(actor)
    if actor.role != Role.INTERN:
        raise Forbidden()
    async with storage.get_store().read() as data:
        intern(data, actor.id)
        return [resource.model_copy(deep=True) for resource in data.resources.values() if resource.team in {None, actor.team}]


async def create_request(actor: User, resource_id: str, level: AccessLevel, justification: str) -> AccessRequest:
    known_actor(actor)
    if actor.role != Role.INTERN:
        raise Forbidden()
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        target = intern(data, actor.id)
        resource = data.resources.get(resource_id)
        if resource is None or resource.team not in {None, target.team}:
            raise NotFound()
        level = access_level.validate_python(level)
        justification = nonempty.validate_python(justification)
        if any(request.intern_id == actor.id and request.resource_id == resource_id
               and request.status != "rejected" for request in data.requests.values()):
            raise Conflict("Заявка на этот ресурс уже существует")
        item = next((item for item in data.items.values()
                     if item.intern_id == actor.id and item.resource_id == resource_id), None)
        automatic = resource.approver == "auto" and level == "read"
        approver_id = None if automatic else target.mentor_id
        approver = DEMO_USERS.get(approver_id)
        if not automatic and (approver is None or approver.role != Role.MENTOR):
            raise Conflict("Для согласования нужен наставник")
        number = max((int(request.id.removeprefix("REQ-")) for request in data.requests.values()), default=1000) + 1
        request = AccessRequest(
            id=f"REQ-{number}", intern_id=actor.id, resource_id=resource_id, level=level,
            justification=justification, status="granted" if automatic else "pending_approval",
            approver_id=approver_id, plan_item_id=item.id if item else None,
            created_day=data.interns[actor.id].current_day, created_at=timestamp(data, actor.id),
            updated_at=timestamp(data, actor.id),
        )
        data.requests[request.id] = request
        payload = {"intern_id": actor.id, "request_id": request.id, "resource_id": resource_id,
                   "status": request.status, "day": request.created_day}
        events._record(data, actor, "access_request_created", payload)
        if request.status == "granted":
            events._record(data, SYSTEM_ACTOR, "access_request_decided", {**payload, "approver": "auto"})
        if item:
            checklist._change_status(data, actor, item, "done" if request.status == "granted" else "waiting",
                                    waiting_for=approver_id)
        return request.model_copy(deep=True)


async def list_requests(actor: User, intern_id: str | None = None) -> list[AccessRequest]:
    known_actor(actor)
    async with storage.get_store().read() as data:
        targets = [intern(data, intern_id)] if intern_id is not None else [intern(data, key) for key in data.interns]
        visible = {target.id for target in targets if can_read_private(actor, target)}
        if not visible:
            raise NotFound()
        return sorted((request.model_copy(deep=True) for request in data.requests.values() if request.intern_id in visible),
                      key=lambda request: (request.created_at, int(request.id.removeprefix("REQ-"))), reverse=True)


async def decide_request(actor: User, request_id: str, approve: bool, reason: str | None = None) -> AccessRequest:
    known_actor(actor)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        request = data.requests.get(request_id)
        if request is None or not can_read_private(actor, intern(data, request.intern_id)):
            raise NotFound()
        if actor.role != Role.MENTOR or request.approver_id != actor.id:
            raise Forbidden()
        if request.status != "pending_approval":
            raise Conflict()
        approve = strict_bool.validate_python(approve)
        reason = None if approve else nonempty.validate_python(reason)
        request.status = "granted" if approve else "rejected"
        request.reject_reason = reason
        request.updated_at = timestamp(data, request.intern_id)
        events._record(data, actor, "access_request_decided", {
            "intern_id": request.intern_id, "request_id": request.id, "resource_id": request.resource_id,
            "status": request.status, "reason": reason, "day": data.interns[request.intern_id].current_day,
        })
        for reminder in data.reminders.values():
            if reminder.request_id == request.id and reminder.status != "done":
                reminder.status, reminder.snooze_until_day = "done", None
                events._record(data, SYSTEM_ACTOR, "reminder_completed", {
                    "intern_id": request.intern_id, "reminder_id": reminder.id,
                    "day": data.interns[request.intern_id].current_day,
                })
        if request.plan_item_id:
            checklist._change_status(data, actor, data.items[request.plan_item_id],
                                    "done" if approve else "in_progress", reason)
        return request.model_copy(deep=True)
