"""SPEC 3.8: отгул на один день — фраза в чате → черновик заявления → подтверждение → решение руководителя."""
from datetime import date

import pytest
from .conftest import as_user

from app.config import settings
from app.llm import get_llm
from app.llm.scenario_provider import _absence_day, _reason

TODAY = date(2026, 11, 11)  # у Ани день 2 при старте 10.11


@pytest.fixture
def scenario(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "scenario")
    get_llm.cache_clear()
    yield client
    get_llm.cache_clear()


def ask(client, text, user="intern-anya"):
    res = client.post("/chat", json={"messages": [{"role": "user", "content": text}]}, headers=as_user(user))
    assert res.status_code == 200
    return res.get_json()


def get(client, url, user):
    return client.get(url, headers=as_user(user))


def post(client, url, body, user):
    return client.post(url, json=body, headers=as_user(user))


def pending(client, user="lead-olga"):
    """В seed уже есть согласованные отгулы прошлых дней — смотрим только новые заявки."""
    return [r for r in get(client, "/absence/requests", user).get_json()["requests"] if r["status"] == "pending"]


@pytest.mark.parametrize("text,expected", [
    ("мне завтра к врачу", date(2026, 11, 12)),
    ("послезавтра нужно отпроситься", date(2026, 11, 13)),
    ("сегодня надо уйти, можно отгул?", TODAY),
    ("отгул на 14.11", date(2026, 11, 14)),
    ("отгул 16 ноября", date(2026, 11, 16)),
    ("отгул на 01.11", date(2026, 11, 12)),  # задним числом нельзя — завтра
    ("отгул на 31.02", date(2026, 11, 12)),  # такой даты нет — завтра
    ("отгул 5 попугаев", date(2026, 11, 12)),
])
def test_absence_day_from_phrase(text, expected):
    assert _absence_day(text, TODAY) == expected


@pytest.mark.parametrize("text,expected", [
    ("мне завтра к врачу", "personal"), ("экзамен в универе", "study"), ("у ребёнка утренник", "family"),
])
def test_reason_is_closed_list(text, expected):
    assert _reason(text) == expected


def test_doctor_phrase_gives_draft_without_medical_details(scenario):
    body = ask(scenario, "Мне завтра к врачу, как отпроситься?")
    [action] = body["actions"]
    assert action["tool"] == "create_absence_request" and action["status"] == "pending"
    assert action["params"] == {"day": "2026-11-12", "reason": "personal"}
    assert "врач" not in action["title"].lower()
    assert "12.11" in action["title"] and "личные дела" in action["title"] and "Ольга Новикова" in action["title"]
    assert "Подтвердить" in body["reply"]
    # без подтверждения руководитель ничего не видит
    assert pending(scenario) == []


def test_full_path_confirm_decide_and_privacy(scenario):
    action = ask(scenario, "мне завтра к врачу")["actions"][0]
    done = post(scenario, f"/actions/{action['id']}/confirm", {}, "intern-anya").get_json()
    assert done["status"] == "done" and done["result"]["request"]["status"] == "pending"

    [req] = pending(scenario)
    assert req["intern_name"] == "Аня Смирнова" and req["reason_title"] == "Личные дела" and req["day"] == "2026-11-12"
    lead_bell = get(scenario, "/reminders", "lead-olga").get_json()["reminders"]
    assert any(r["kind"] == "absence_new" for r in lead_bell)

    # чужие не видят и не решают: наставник, другой руководитель, сам стажёр
    assert get(scenario, "/absence/requests", "mentor-petr").status_code == 404
    assert all(r["intern_id"] != "intern-anya" for r in get(scenario, "/absence/requests", "lead-sergey").get_json()["requests"])
    for user in ("intern-anya", "mentor-petr", "lead-sergey"):
        assert post(scenario, f"/absence/requests/{req['id']}/decide", {"approve": True}, user).status_code == 404

    decided = post(scenario, f"/absence/requests/{req['id']}/decide", {"approve": True}, "lead-olga")
    assert decided.status_code == 200 and decided.get_json()["status"] == "approved"
    assert post(scenario, f"/absence/requests/{req['id']}/decide", {"approve": False}, "lead-olga").status_code == 409

    bell = get(scenario, "/reminders", "intern-anya").get_json()["reminders"]
    assert any(r["kind"] == "absence_decided" and "согласован" in r["text"] for r in bell)
    facts = get(scenario, "/absence/facts?intern_id=intern-anya", "mentor-petr").get_json()
    assert {"intern_id": "intern-anya", "day": "2026-11-12"} in facts["facts"]
    assert all(set(f) == {"intern_id", "day"} for f in facts["facts"])  # без причины и номера заявки
    assert get(scenario, "/absence/facts?intern_id=intern-anya", "mentor-maria").status_code == 404
    assert get(scenario, "/absence/facts", "mentor-petr").status_code == 404


def test_decide_requires_strict_bool(scenario):
    action = ask(scenario, "мне завтра к врачу")["actions"][0]
    post(scenario, f"/actions/{action['id']}/confirm", {}, "intern-anya")
    [req] = pending(scenario)
    assert post(scenario, f"/absence/requests/{req['id']}/decide", {"approve": "yes"}, "lead-olga").status_code == 422


def test_sick_leave_and_vacation_still_go_to_hr(scenario):
    for text in ("Я заболел, как оформить больничный?", "Как оформить отпуск?"):
        body = ask(scenario, text)
        assert body["actions"] == [] and "HR BP" in body["reply"]


def test_lead_and_mentor_get_hr_answer_without_draft(scenario):
    for user in ("lead-olga", "mentor-petr"):
        body = ask(scenario, "как взять отгул?", user)
        assert body["actions"] == []


def test_button_draft_and_past_day_fails_on_confirm(scenario):
    res = post(scenario, "/actions", {"tool": "create_absence_request", "params": {"day": "2026-11-01"}}, "intern-anya")
    assert res.status_code == 201
    done = post(scenario, f"/actions/{res.get_json()['id']}/confirm", {}, "intern-anya").get_json()
    assert done["status"] == "failed" and "задним числом" in done["error"]
    assert post(scenario, "/actions", {"tool": "create_absence_request", "params": {"day": "2026-11-20"}},
                "mentor-petr").status_code == 403


def test_duplicate_day_fails_with_clear_message(scenario):
    ids = [ask(scenario, "мне завтра к врачу")["actions"][0]["id"] for _ in range(2)]
    assert post(scenario, f"/actions/{ids[0]}/confirm", {}, "intern-anya").get_json()["status"] == "done"
    second = post(scenario, f"/actions/{ids[1]}/confirm", {}, "intern-anya").get_json()
    assert second["status"] == "failed" and "уже запрошен" in second["error"]


def test_plan_context_has_today_for_model(scenario):
    from app import async_runner
    from app.agent.onboarding_tools import plan_context
    from app.agent.users import DEMO_USERS
    assert "Сегодня: 2026-11-11." in async_runner.run(plan_context(DEMO_USERS["intern-anya"]))
