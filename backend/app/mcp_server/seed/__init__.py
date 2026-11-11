"""Единственный синтетический корпус для обеих будущих реализаций хранилища."""
import json
from pathlib import Path

from app.agent.users import DEMO_USERS, User

from .. import checklist, events, storage
from .._domain import known_actor, owner_id, timestamp
from .._system import SYSTEM_ACTOR
from ..models import AccessRequest, AccessResource, InternState, OnboardingData, PlanItem, SkillProfile

SEED_PATH = Path(__file__).with_name("onboarding.json")


def load_seed() -> OnboardingData:
    source = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    data = OnboardingData()
    for resource in source["resources"]:
        model = AccessResource.model_validate({"fields": source["request_fields"], **resource})
        data.resources[model.id] = model
    for entry in source["interns"]:
        user = DEMO_USERS[entry["id"]]
        state = InternState(intern_id=user.id, start_date=entry["start_date"], current_day=entry["current_day"])
        data.interns[user.id] = state
        prefix = user.id.removeprefix("intern-")
        templates = source["common_items"] + source["team_items"][user.team] + source["outline_items"]
        for template in templates:
            item = PlanItem.model_validate({**template, "id": f"{prefix}.{template['id']}",
                "intern_id": user.id, "summary": f"{source['notice']}. {template['summary']}",
                "updated_at": timestamp(data, user.id, 1)})
            data.items[item.id] = item
            if template["id"] in entry["done_items"]:
                checklist._change_status(data, DEMO_USERS[owner_id(item)], item, "done", day=1)
        data.profiles[user.id] = SkillProfile(
            intern_id=user.id, skills=entry["skills"], strengths=entry["strengths"], growth=entry["growth"],
            updated_at=timestamp(data, user.id, 1),
        )
    for entry in source["requests"]:
        user = DEMO_USERS[entry["intern_id"]]
        item = next((item for item in data.items.values()
                     if item.intern_id == user.id and item.resource_id == entry["resource_id"]), None)
        request = AccessRequest.model_validate({**entry, "approver_id": user.mentor_id if entry["status"] == "pending_approval" else None,
            "plan_item_id": item.id if item else None, "created_at": timestamp(data, user.id, entry["created_day"]),
            "updated_at": timestamp(data, user.id, entry["created_day"])})
        data.requests[request.id] = request
        payload = {"intern_id": user.id, "request_id": request.id, "resource_id": request.resource_id,
                   "status": request.status, "day": request.created_day}
        events._record(data, user, "access_request_created", payload)
        if request.status == "granted":
            events._record(data, SYSTEM_ACTOR, "access_request_decided", {**payload, "approver": "auto"})
        if item and request.status == "pending_approval":
            checklist._change_status(data, user, item, "waiting", waiting_for=user.mentor_id, day=request.created_day)
    return data


async def reset_demo(actor: User) -> None:
    known_actor(actor)
    store = storage.get_store()
    seed = await store.seed_for_schema(load_seed())
    async with store.transaction() as data:
        for field in OnboardingData.model_fields:
            setattr(data, field, getattr(seed, field))
        events._record(data, actor, "demo_reset", {})
