import asyncio

import pytest
from pydantic import ValidationError

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, events, hiring
from app.mcp_server.errors import Conflict, NotFound
from app.mcp_server.models import AccessRequest

run = async_runner.run
ANYA = DEMO_USERS["intern-anya"]
PETR = DEMO_USERS["mentor-petr"]
IVAN = DEMO_USERS["intern-ivan"]
MARIA = DEMO_USERS["mentor-maria"]


def test_auto_request_updates_plan_and_records_facts(store, snapshot):
    request = run(access.create_request(ANYA, "jira", "read", "  Для учебной задачи  "))
    assert request.id.startswith("REQ-") and request.status == "granted"
    assert request.justification == "Для учебной задачи" and request.approver_id is None
    data = snapshot()
    assert data.items[request.plan_item_id].status == "done"
    assert [event.type for event in data.events[-3:]] == ["access_request_created", "access_request_decided", "plan_item_status_changed"]
    assert data.events[-3].user_id == ANYA.id and data.events[-1].user_id == ANYA.id
    assert data.events[-2].user_id == "system" and data.events[-2].role == "system"
    assert run(checklist.get_plan(ANYA, ANYA.id)).next_step.item.resource_id == "bitbucket-platform"


def test_approval_flow_and_decision_is_final(store, snapshot):
    request = run(access.create_request(ANYA, "bitbucket-platform", "edit", "Учебный код"))
    assert request.status == "pending_approval" and request.approver_id == PETR.id
    assert snapshot().items[request.plan_item_id].status == "waiting"
    result = run(access.decide_request(PETR, request.id, True))
    assert result.status == "granted" and result.reject_reason is None
    assert snapshot().items[request.plan_item_id].status == "done"
    before = snapshot()
    with pytest.raises(Conflict):
        run(access.decide_request(PETR, request.id, False, "передумал"))
    assert snapshot() == before


@pytest.mark.parametrize("reason", [None, "", " \n "])
def test_reject_requires_reason_and_does_not_mutate(store, snapshot, reason):
    before = snapshot()
    with pytest.raises(ValidationError):
        run(access.decide_request(MARIA, "REQ-1001", False, reason))
    assert snapshot() == before


def test_rejection_returns_item_and_allows_new_request(store, snapshot):
    rejected = run(access.decide_request(MARIA, "REQ-1001", False, "Уточни учебную задачу"))
    assert rejected.reject_reason == "Уточни учебную задачу"
    item = snapshot().items[rejected.plan_item_id]
    assert item.status == "in_progress" and item.status_reason == rejected.reject_reason
    assert item.waiting_for is None
    retry = run(access.create_request(IVAN, "bitbucket-delivery", "read", "Уточнённая задача"))
    assert retry.id != rejected.id and retry.status == "pending_approval"
    assert run(access.list_requests(MARIA))[0].id == retry.id


def test_resource_approver_is_configuration_not_kind(store, edit):
    edit(lambda data: setattr(data.resources["jira"], "approver", "mentor"))
    assert run(access.create_request(ANYA, "jira", "read", "Учебная задача")).status == "pending_approval"
    edit(lambda data: setattr(data.resources["bitbucket-platform"], "approver", "auto"))
    assert run(access.create_request(ANYA, "bitbucket-platform", "admin", "Учебная задача")).status == "granted"


def test_requests_sorted_newest_and_no_linked_item_is_allowed(store):
    first = run(access.create_request(ANYA, "jira", "read", "Учебная задача"))
    second = run(access.create_request(ANYA, "confluence", "read", "Учебные документы"))
    assert second.plan_item_id is None
    assert [request.id for request in run(access.list_requests(ANYA))] == [second.id, first.id]
    assert {request.intern_id for request in run(access.list_requests(PETR))} == {ANYA.id}


@pytest.mark.parametrize("resource", ["missing", "bitbucket-delivery"])
def test_unknown_and_foreign_resource_identical(store, snapshot, resource):
    before = snapshot()
    with pytest.raises(NotFound) as error:
        run(access.create_request(ANYA, resource, "read", "Учебная задача"))
    assert str(error.value) == "Не найдено" and snapshot() == before


@pytest.mark.parametrize("level,reason", [("root", "text"), ("read", ""), ("read", " "), ("read", None)])
def test_request_validation_is_atomic(store, snapshot, level, reason):
    before = snapshot()
    with pytest.raises(ValidationError):
        run(access.create_request(ANYA, "jira", level, reason))
    assert snapshot() == before


def test_concurrent_duplicate_request_has_one_winner(store, snapshot):
    async def submit():
        return await asyncio.gather(*(access.create_request(ANYA, "jira", "read", "Учебная задача")
                                      for _ in range(2)), return_exceptions=True)
    results = run(submit())
    assert sum(isinstance(result, AccessRequest) for result in results) == 1
    assert sum(isinstance(result, Conflict) for result in results) == 1
    assert len([request for request in snapshot().requests.values() if request.intern_id == ANYA.id]) == 1


def test_atomic_request_plan_and_event_rollback(store, snapshot, monkeypatch):
    before = snapshot()
    original = events._record
    def broken(data, actor, type, payload):
        result = original(data, actor, type, payload)
        if type == "plan_item_status_changed":
            raise RuntimeError("failed event write")
        return result
    monkeypatch.setattr(events, "_record", broken)
    with pytest.raises(RuntimeError):
        run(access.create_request(ANYA, "jira", "read", "Учебная задача"))
    assert snapshot() == before


def test_skill_profiles_differ_and_only_skill_changes(store, snapshot):
    a = run(hiring.get_skill_profile(ANYA, ANYA.id))
    b = run(hiring.get_skill_profile(IVAN, IVAN.id))
    assert a.skills == {"git": "novice", "sql": "confident"}
    assert b.skills == {"git": "confident", "sql": "novice"}
    updated = run(hiring.set_skill_level(PETR, ANYA.id, "git", "familiar"))
    assert updated.updated_by == PETR.id
    assert updated.strengths == a.strengths and updated.growth == a.growth
    before = snapshot()
    run(hiring.set_skill_level(PETR, ANYA.id, "git", "familiar"))
    assert snapshot() == before
    for topic, level in [(" ", "novice"), ("git", "expert")]:
        with pytest.raises(ValidationError):
            run(hiring.set_skill_level(PETR, ANYA.id, topic, level))
        assert snapshot() == before


def test_missing_objects_do_not_reveal_data(store, edit):
    for operation in (lambda: hiring.get_skill_profile(PETR, "intern-missing"),
                      lambda: access.list_requests(PETR, "intern-missing"),
                      lambda: access.decide_request(PETR, "REQ-404", True)):
        with pytest.raises(NotFound):
            run(operation())
    edit(lambda data: data.profiles.pop(ANYA.id))
    with pytest.raises(NotFound):
        run(hiring.get_skill_profile(ANYA, ANYA.id))
    with pytest.raises(NotFound):
        run(hiring.set_skill_level(PETR, ANYA.id, "git", "novice"))


def test_decision_validation_does_not_accept_truthy_strings(store, snapshot):
    before = snapshot()
    with pytest.raises(ValidationError):
        run(access.decide_request(MARIA, "REQ-1001", "yes"))
    assert snapshot() == before
