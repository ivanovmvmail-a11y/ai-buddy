"""Напоминание по просьбе стажёра (kind=custom, миграция 20261113150000) — в памяти и в PostgreSQL."""
from datetime import timedelta

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import clock
from app.mcp_server.seed import load_seed

run = async_runner.run
ANYA = DEMO_USERS["intern-anya"]


def custom(user=ANYA):
    return [r for r in run(clock.list_reminders(user)) if r.kind == "custom"]


def test_custom_reminder_waits_for_its_day(store, snapshot):
    day = run(clock.get_day(ANYA, ANYA.id))
    today = load_seed().interns[ANYA.id].start_date + timedelta(days=day - 1)
    made = run(clock.add_custom_reminder(ANYA, "про 1:1 с наставником", today + timedelta(days=1)))
    [saved] = custom()
    assert saved.id == made.id and saved.status == "snoozed" and saved.snooze_until_day == day + 1
    run(clock.advance_day(ANYA, ANYA.id))
    [saved] = custom()
    assert saved.status == "active" and saved.text == "Ты просил(а) напомнить про 1:1 с наставником"
    assert saved.action.target == "plan" and saved.intern_id == ANYA.id
    run(clock.done_reminder(ANYA, saved.id))
    assert custom()[0].status == "done"
