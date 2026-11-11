"""Регрессии ревью PR #17: пункты 1–5, 7–9. Пункт 6 передан T3."""
import pytest
from pydantic import TypeAdapter, ValidationError

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import _domain, access, checklist, clock, events, hiring, storage
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import Forbidden, NotFound
from app.mcp_server.models import SystemActor
from app.mcp_server.seed import load_seed
from app.mcp_server.seed.__main__ import main

run = async_runner.run
ANYA = DEMO_USERS["intern-anya"]
PETR = DEMO_USERS["mentor-petr"]


def advance_to(day):
    while run(clock.get_day(ANYA, ANYA.id)) < day:
        run(clock.advance_day(ANYA, ANYA.id))


def status_ids(summary):
    return ({fact["item_id"] for fact in summary["closed"]}, {item.id for item in summary["carry_over"]})


def test_r1_waiting_request_reminder_is_not_preempted_by_overdue(store, snapshot):
    advance_to(4)
    request = run(access.create_request(ANYA, "bitbucket-platform", "read", "Учебная задача"))
    run(clock.advance_day(ANYA, ANYA.id))
    assert not any(reminder.plan_item_id == request.plan_item_id for reminder in snapshot().reminders.values())
    run(clock.advance_day(ANYA, ANYA.id))
    reminders = [reminder for reminder in snapshot().reminders.values() if reminder.plan_item_id == request.plan_item_id]
    assert len(reminders) == 1
    assert reminders[0].request_id == request.id and reminders[0].created_day == 6
    assert "Напомнить наставнику?" in reminders[0].text
    assert "прошёл срок" not in reminders[0].text
    run(clock.advance_day(ANYA, ANYA.id))
    assert sum(reminder.plan_item_id == request.plan_item_id for reminder in snapshot().reminders.values()) == 1


def test_r2_closed_then_returned_in_same_week_is_only_carry_over(store):
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    advance_to(3)
    run(checklist.set_item_status(PETR, "anya.w1.notes", "in_progress", "Дополнить конспект"))
    summary = run(checklist.weekly_summary(ANYA, ANYA.id, 1))
    closed, carry = status_ids(summary)
    assert "anya.w1.notes" not in closed and "anya.w1.notes" in carry
    assert closed.isdisjoint(carry)
    item = next(item for item in summary["carry_over"] if item.id == "anya.w1.notes")
    assert item.status_reason == "Дополнить конспект" and item.updated_by == PETR.id


def test_r2_week_one_remains_unchanged_after_week_two_completion(store):
    advance_to(7)
    before = run(checklist.weekly_summary(ANYA, ANYA.id, 1))
    advance_to(9)
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    after = run(checklist.weekly_summary(ANYA, ANYA.id, 1))
    assert after == before
    closed, carry = status_ids(after)
    assert "anya.w1.notes" in carry and "anya.w1.notes" not in closed
    historical = next(item for item in after["carry_over"] if item.id == "anya.w1.notes")
    assert historical.status == "not_started" and historical.overdue
    week_two = run(checklist.weekly_summary(ANYA, ANYA.id, 2))
    assert "anya.w1.notes" in status_ids(week_two)[0]
    assert "anya.w1.notes" not in status_ids(week_two)[1]


def test_r2_week_one_close_survives_later_return_and_reclose(store):
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    advance_to(7)
    expected = run(checklist.weekly_summary(ANYA, ANYA.id, 1))
    advance_to(8)
    run(checklist.set_item_status(PETR, "anya.w1.notes", "in_progress", "Уточнить пример"))
    assert run(checklist.weekly_summary(ANYA, ANYA.id, 1)) == expected
    assert "anya.w1.notes" in status_ids(run(checklist.weekly_summary(ANYA, ANYA.id, 2)))[1]
    # Внутри одного дня учитывается порядок событий, а не только дата.
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    closed, carry = status_ids(run(checklist.weekly_summary(ANYA, ANYA.id, 2)))
    assert "anya.w1.notes" in closed and "anya.w1.notes" not in carry


def test_r2_waiting_metadata_is_replayed_at_week_boundary(store):
    advance_to(4)
    request = run(access.create_request(ANYA, "bitbucket-platform", "read", "Учебная задача"))
    advance_to(7)
    expected = run(checklist.weekly_summary(ANYA, ANYA.id, 1))
    advance_to(9)
    run(access.decide_request(PETR, request.id, True))
    actual = run(checklist.weekly_summary(ANYA, ANYA.id, 1))
    assert actual == expected
    waiting = next(item for item in actual["carry_over"] if item.id == request.plan_item_id)
    assert waiting.status == "waiting" and waiting.waiting_for == PETR.id and waiting.waiting_days == 3
    assert request.id not in {fact["request_id"] for fact in actual["access_granted"]}


def test_r3_reminder_actions_have_intern_day_and_virtual_timestamp(store):
    reminders = run(clock.cron_tick(SYSTEM_ACTOR))
    ivan = DEMO_USERS["intern-ivan"]
    reminder = next(reminder for reminder in reminders if reminder.request_id == "REQ-1001")
    run(clock.snooze_reminder(ivan, reminder.id, 2))
    run(clock.done_reminder(ivan, reminder.id))
    recorded = run(events.list_events(SYSTEM_ACTOR, ivan.id))
    actions = [event for event in recorded if event.type in {"reminder_snoozed", "reminder_completed"}
               and event.payload.get("reminder_id") == reminder.id]
    assert {event.type for event in actions} == {"reminder_snoozed", "reminder_completed"}
    for event in actions:
        assert event.payload["intern_id"] == ivan.id and event.payload["day"] == 8
        assert event.ts.isoformat() == "2026-11-11T12:00:00+00:00"
        assert event.user_id == ivan.id


def test_r3_automatic_completion_and_reactivation_are_scoped(store):
    reminder = next(reminder for reminder in run(clock.cron_tick(SYSTEM_ACTOR)) if reminder.request_id == "REQ-1001")
    ivan = DEMO_USERS["intern-ivan"]
    run(clock.snooze_reminder(ivan, reminder.id))
    run(clock.advance_day(ivan, ivan.id))
    run(access.decide_request(DEMO_USERS["mentor-maria"], "REQ-1001", True))
    changes = run(events.list_events(SYSTEM_ACTOR, ivan.id))
    for kind in ("reminder_reactivated", "reminder_completed"):
        event = next(event for event in changes if event.type == kind and event.payload.get("reminder_id") == reminder.id)
        assert event.payload["day"] == 9 and event.ts.date().isoformat() == "2026-11-12"
        assert event.user_id == "system" and event.role == "system"


def test_r4_cron_and_auto_decisions_use_system_but_human_actions_keep_actor(store):
    run(clock.advance_day(ANYA))
    recorded = run(events.list_events(SYSTEM_ACTOR))
    cron = [event for event in recorded if event.type == "reminder_created"]
    assert cron and all(event.user_id == "system" and event.role == "system" for event in cron)
    assert any(event.type == "day_advanced" and event.user_id == ANYA.id for event in recorded)
    request = run(access.create_request(ANYA, "jira", "read", "Учебная задача"))
    decision = next(event for event in run(events.list_events(SYSTEM_ACTOR))
                    if event.type == "access_request_decided" and event.payload.get("request_id") == request.id)
    assert decision.user_id == "system" and decision.role == "system"


@pytest.mark.parametrize("actor", [DEMO_USERS["intern-anya"], SystemActor(),
    DEMO_USERS["intern-anya"].model_copy(update={"id": "system", "role": "system"})])
def test_r4_system_identity_cannot_be_forged_from_payload(store, actor):
    for operation in (lambda: clock.cron_tick(actor), lambda: events.log_event(actor, "forged", {}),
                      lambda: events.list_events(actor)):
        with pytest.raises(Forbidden):
            run(operation())
    with pytest.raises(ValidationError):
        SYSTEM_ACTOR.id = "intern-anya"


def test_r5_cli_validation_does_not_initialize_or_mutate_store(store, snapshot, monkeypatch, capsys):
    before = snapshot()
    def fail():
        pytest.fail("Validation-only CLI must not initialize a store")
    monkeypatch.setattr(storage, "get_store", fail)
    main(["--validate"])
    output = capsys.readouterr().out
    assert "Seed validated" in output and "validation only" in output
    assert "no server or database was populated" in output
    assert snapshot() == before


def test_r7_service_calls_reuse_compiled_validation_adapters(store, monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail("TypeAdapter must be compiled once at module import")
    monkeypatch.setattr(TypeAdapter, "__init__", fail)
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    request = run(access.create_request(ANYA, "bitbucket-platform", "read", "Учебная задача"))
    run(access.decide_request(PETR, request.id, True))
    run(hiring.set_skill_level(PETR, ANYA.id, "git", "familiar"))


def test_r8_plan_uses_assigned_lead_not_team_and_preserves_private_role_filter(store, monkeypatch):
    target = ANYA.model_copy(update={"lead_id": "lead-sergey"})
    monkeypatch.setitem(DEMO_USERS, ANYA.id, target)
    with pytest.raises(NotFound):
        run(checklist.get_plan(DEMO_USERS["lead-olga"], ANYA.id))
    assert run(checklist.get_plan(DEMO_USERS["lead-sergey"], ANYA.id)).intern_id == ANYA.id
    for actor_id in ("lead-sergey", "curator-dmitry", "hrbp-elena"):
        with pytest.raises(NotFound):
            run(hiring.get_skill_profile(DEMO_USERS[actor_id], ANYA.id))


def test_r9_seed_passes_historical_day_without_temporarily_advancing_clock(monkeypatch):
    original = checklist._change_status
    seen = []
    def checked(data, actor, item, status, *args, **kwargs):
        assert data.interns[item.intern_id].current_day == {"intern-anya": 2, "intern-ivan": 8}[item.intern_id]
        assert kwargs["day"] == (5 if status == "waiting" else 1)
        seen.append((item.id, kwargs["day"]))
        return original(data, actor, item, status, *args, **kwargs)
    monkeypatch.setattr(checklist, "_change_status", checked)
    data = load_seed()
    assert ("ivan.w1.team-space", 5) in seen
    assert data.interns["intern-ivan"].current_day == 8
    assert _domain.item_view(data, data.items["ivan.w1.team-space"]).waiting_days == 3
