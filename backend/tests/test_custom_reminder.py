"""Напоминание по просьбе стажёра (HANDOFF 13.11 п. 2, Claude 13.11): «напомни в пятницу про 1:1» → черновик →
«Подтвердить» → в этот демо-день напоминание приходит в колокольчик; отложить/готово — как у остальных."""
from datetime import date, timedelta

import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.llm.scenario_provider import reminder_plan
from app.mcp_server import clock
from app.mcp_server.errors import Conflict, Forbidden
from app.mcp_server.seed import load_seed

from .conftest import as_user
from .test_scenario_provider import ask, scenario  # noqa: F401 — фикстура сценарного режима

run = async_runner.run


def bell(client, user="intern-anya"):
    return [r for r in client.get("/reminders", headers=as_user(user)).get_json()["reminders"] if r["kind"] == "custom"]


def today(client, user="intern-anya"):
    return date.fromisoformat(client.get("/plan", headers=as_user(user)).get_json()["today"]) \
        if "today" in client.get("/plan", headers=as_user(user)).get_json() else None


def next_day(client, user="intern-anya"):
    assert client.post("/demo/next-day", json={"intern_id": user}, headers=as_user(user)).status_code == 200


@pytest.mark.parametrize("phrase, shift, text", [
    ("напомни мне в пятницу про 1:1 с наставником", None, "про 1:1 с наставником"),
    ("Напомни завтра утром оформить пропуск", 1, "оформить пропуск"),
    ("напомни послезавтра о встрече", 2, "о встрече"),
    ("поставь напоминание через 3 дня — проверить заявку", 3, "проверить заявку"),
    ("напомни через неделю про ретро", 7, "про ретро"),
])
def test_phrase_to_date_and_text(phrase, shift, text):
    friday_before = date(2026, 11, 12)  # четверг
    day, got = reminder_plan(phrase, friday_before)
    assert got == text
    assert day == (date(2026, 11, 13) if shift is None else friday_before + timedelta(days=shift))


def test_without_subject_asks_what_to_remind():
    day, reply = reminder_plan("напомни мне завтра", date(2026, 11, 12))
    assert day is None and "О чём напомнить" in reply


def test_full_loop_draft_confirm_bell_on_that_day(scenario):
    res = ask(scenario, "напомни мне послезавтра про 1:1 с наставником")
    assert "Подготовил напоминание" in res["reply"] and "Подтвердить" in res["reply"]
    [action] = res["actions"]
    assert action["tool"] == "create_reminder" and action["title"].endswith("про 1:1 с наставником")
    assert bell(scenario) == []  # до подтверждения ничего нет

    done = scenario.post(f"/actions/{action['id']}/confirm", headers=as_user("intern-anya")).get_json()
    assert done["status"] == "done" and done["result"]["status"] == "created"
    assert bell(scenario) == []  # ещё не тот день

    next_day(scenario)
    assert bell(scenario) == []
    next_day(scenario)
    [note] = bell(scenario)  # послезавтра наступило — пришло
    assert note["text"] == "Ты просил(а) напомнить про 1:1 с наставником" and note["action"]["label"] == "Открыть"

    # «Напомнить завтра» и «Готово» — как у остальных уведомлений
    assert scenario.post(f"/reminders/{note['id']}/snooze", headers=as_user("intern-anya")).status_code == 200
    assert bell(scenario) == []
    next_day(scenario)
    assert [r["id"] for r in bell(scenario)] == [note["id"]]
    assert scenario.post(f"/reminders/{note['id']}/done", headers=as_user("intern-anya")).status_code == 200
    assert bell(scenario) == []
    assert bell(scenario, "intern-kirill") == []  # чужим не видно


def test_today_reminder_is_active_at_once(scenario):
    [action] = ask(scenario, "напомни сегодня выложить демо")["actions"]
    scenario.post(f"/actions/{action['id']}/confirm", headers=as_user("intern-anya"))
    [note] = bell(scenario)
    assert note["text"] == "Ты просил(а) напомнить: выложить демо"


def test_other_roles_get_honest_answer_no_tool(scenario):
    for user in ("mentor-petr", "lead-olga", "curator-dmitry"):
        res = ask(scenario, "напомни мне в пятницу про встречу", user)
        assert res["actions"] == [] and "календарь" in res["reply"]


def test_service_rules(scenario):
    anya = DEMO_USERS["intern-anya"]
    current = run(clock.get_day(anya, anya.id))
    start = load_seed().interns[anya.id].start_date
    today_date = start + timedelta(days=current - 1)
    with pytest.raises(Conflict):
        run(clock.add_custom_reminder(anya, "вчерашнее", today_date - timedelta(days=1)))
    with pytest.raises(Conflict):
        run(clock.add_custom_reminder(anya, "слишком далеко", today_date + timedelta(days=61)))
    with pytest.raises(Conflict):
        run(clock.add_custom_reminder(anya, "   ", today_date))
    with pytest.raises(Forbidden):
        run(clock.add_custom_reminder(DEMO_USERS["mentor-petr"], "себе", today_date))
    later = run(clock.add_custom_reminder(anya, "что  в среду   демо", today_date + timedelta(days=5)))
    assert later.status == "snoozed" and later.snooze_until_day == current + 5
    assert later.text == "Ты просил(а) напомнить, что в среду демо"
