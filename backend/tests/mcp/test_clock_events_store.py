import asyncio
from datetime import datetime, timezone
import inspect

import pytest
from pydantic import ValidationError

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock, events, hiring, storage
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import Conflict, Forbidden, NotFound
from app.mcp_server.models import OnboardingData
from app.mcp_server.seed import load_seed
from app.mcp_server.seed.__main__ import main

run = async_runner.run
ANYA = DEMO_USERS["intern-anya"]
IVAN = DEMO_USERS["intern-ivan"]
MARIA = DEMO_USERS["mentor-maria"]


def tick(day=None):
    return run(clock.cron_tick(SYSTEM_ACTOR, day))


def test_pending_reminder_once_and_snooze_reuses_same_object(store, snapshot):
    created = tick()
    waiting = next(reminder for reminder in created if reminder.request_id == "REQ-1001")
    assert waiting.user_id == IVAN.id and "напомнить" in waiting.text.lower()
    assert tick() == []
    snoozed = run(clock.snooze_reminder(IVAN, waiting.id, 2))
    assert snoozed.snooze_until_day == 10
    run(clock.advance_day(IVAN, IVAN.id))
    assert next(reminder for reminder in run(clock.list_reminders(IVAN)) if reminder.id == waiting.id).status == "snoozed"
    run(clock.advance_day(IVAN, IVAN.id))
    assert snapshot().reminders[waiting.id].status == "active"
    assert sum(event.type == "reminder_created" and event.payload["item_id"] == waiting.plan_item_id
               for event in snapshot().events) == 1
    run(clock.done_reminder(IVAN, waiting.id))
    tick(30)
    assert sum(reminder.plan_item_id == waiting.plan_item_id for reminder in snapshot().reminders.values()) == 1
    assert snapshot().reminders[waiting.id].status == "done"
    with pytest.raises(Conflict):
        run(clock.snooze_reminder(IVAN, waiting.id))


def test_reminders_created_at_two_days_and_sent_to_item_owner(store, edit, snapshot):
    def prepare(data):
        data.interns[IVAN.id].current_day = 6
        data.items["ivan.w1.channels"].status = "not_started"
    edit(prepare)
    created = tick()
    assert not any(reminder.request_id == "REQ-1001" for reminder in created)
    assert any(reminder.plan_item_id == "ivan.w1.channels" and reminder.user_id == MARIA.id for reminder in created)
    assert not any(reminder.plan_item_id == "ivan.w1.team-space" for reminder in created)
    # В день 7 заявке два дня: появляется именно напоминание о согласовании.
    run(clock.advance_day(IVAN, IVAN.id))
    assert any(reminder.request_id == "REQ-1001" for reminder in snapshot().reminders.values())
    assert len({reminder.plan_item_id for reminder in snapshot().reminders.values()}) == len(snapshot().reminders)


def test_grant_and_manual_completion_resolve_reminders(store, snapshot):
    tick()
    run(access.decide_request(MARIA, "REQ-1001", True))
    run(checklist.set_item_status(IVAN, "ivan.w1.notes", "done"))
    for reminder in snapshot().reminders.values():
        if reminder.plan_item_id in {"ivan.w1.team-space", "ivan.w1.notes"}:
            assert reminder.status == "done"
    tick()


def test_rejection_resolves_waiting_reminder(store, snapshot):
    tick()
    waiting = next(reminder for reminder in snapshot().reminders.values() if reminder.request_id == "REQ-1001")
    run(access.decide_request(MARIA, "REQ-1001", False, "Уточни цель доступа"))
    assert snapshot().reminders[waiting.id].status == "done"
    assert snapshot().items[waiting.plan_item_id].status == "in_progress"


def test_clock_and_reminder_invalid_inputs_do_not_mutate(store, snapshot):
    before = snapshot()
    for operation in (lambda: clock.get_day(ANYA, "missing"), lambda: clock.advance_day(ANYA, "missing")):
        with pytest.raises(NotFound):
            run(operation())
    assert snapshot() == before
    with pytest.raises(ValidationError):
        tick(0)
    tick()
    reminder = run(clock.list_reminders(IVAN))[0]
    before = snapshot()
    for days in (0, -1, True, 1.5):
        with pytest.raises(ValidationError):
            run(clock.snooze_reminder(IVAN, reminder.id, days))
        assert snapshot() == before
    run(clock.done_reminder(IVAN, reminder.id))
    before = snapshot()
    run(clock.done_reminder(IVAN, reminder.id))
    assert snapshot() == before


def test_system_events_fields_filter_and_actor_is_explicit(store):
    async def exercise():
        event = await events.log_event(SYSTEM_ACTOR, "test_event", {"intern_id": ANYA.id, "day": 2, "nested": {"values": [1, True, None]}})
        assert event.user_id == "system" and event.team == "system" and event.role == "system"
        assert event.ts.tzinfo is not None
        result = await events.list_events(SYSTEM_ACTOR, ANYA.id, "test_event")
        assert result == [event]
        assert await events.list_events(SYSTEM_ACTOR, IVAN.id, "test_event") == []
        with pytest.raises(ValidationError):
            await events.log_event(SYSTEM_ACTOR, " ", {})
        with pytest.raises(Forbidden):
            await events.list_events(ANYA)
    run(exercise())


def test_store_snapshots_rollback_isolation_and_idempotent_seed(store, snapshot):
    before = snapshot()
    async def exercise():
        with pytest.raises(RuntimeError):
            async with store.transaction() as data:
                data.items.clear()
                raise RuntimeError("rollback")
        async with store.transaction() as data:
            returned = data.items["anya.w1.notes"]
        returned.status = "done"
        await store.initialize(load_seed())
    run(exercise())
    assert snapshot() == before
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    changed = snapshot()
    run(store.initialize(load_seed()))
    assert snapshot() == changed
    reset_at = datetime.now(timezone.utc)
    run(store.initialize(load_seed(), reset=True))
    reset = snapshot()
    assert reset.model_dump(exclude={"events"}) == before.model_dump(exclude={"events"})
    assert [e.model_dump(exclude={"ts"}) for e in reset.events] == [e.model_dump(exclude={"ts"}) for e in before.events]
    assert all(reset_at <= e.ts <= datetime.now(timezone.utc) for e in reset.events)
    empty = storage.InMemoryStore()
    run(empty.initialize(load_seed()))
    async def count():
        async with empty.transaction() as data:
            return len(data.interns)
    assert run(count()) == len(before.interns)


def test_store_factory_cached_and_selects_backend_without_connecting(monkeypatch, caplog):
    # Этот тест использует настоящую фабрику, а не фикстуру store.
    from app.config import settings
    storage.get_store.cache_clear()
    from app.mcp_server.postgres import PostgresStore
    monkeypatch.setattr(settings, "database_url", "")
    try:
        first = storage.get_store()
        assert storage.get_store() is first
        assert isinstance(first, storage.InMemoryStore)
        assert "lost on restart" in caplog.text
        storage.get_store.cache_clear()
        monkeypatch.setattr(settings, "database_url", "postgresql://must-not-connect.invalid/db")
        postgres = storage.get_store()
        assert isinstance(postgres, storage.DemoStore) and storage.get_store() is postgres
        assert isinstance(postgres.primary, PostgresStore)
        assert postgres.primary._pool is None
    finally:
        storage.get_store.cache_clear()


@pytest.mark.parametrize("args", [[], ["--reset"]])
def test_seed_cli_explicitly_reports_memory_only(store, capsys, args):
    main(args)
    output = capsys.readouterr().out
    assert ("seed reset" if args else "existing data preserved") in output
    assert type(store).__name__ in output


def test_public_service_contracts_are_async_and_actor_first():
    functions = [checklist.get_plan, checklist.set_item_status, checklist.weekly_summary,
                 access.list_resources, access.create_request, access.list_requests, access.decide_request,
                 hiring.get_skill_profile, hiring.set_skill_level, clock.get_day, clock.advance_day,
                 clock.cron_tick, clock.reset_demo, clock.list_reminders, clock.snooze_reminder,
                 clock.done_reminder, events.log_event, events.list_events]
    for function in functions:
        assert inspect.iscoroutinefunction(function)
        assert next(iter(inspect.signature(function).parameters)) == "actor"
