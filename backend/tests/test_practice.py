"""Спека 107: практическое задание с проверкой результата — без модели, только свой пункт."""
import json

import pytest

from app import async_runner
from app.agent import practice
from app.mcp_server import events
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.seed import SEED_PATH

from .conftest import as_user

GIT = "Создай учебную ветку, коммит и pull request."
CI = "Найди упавший шаг учебного пайплайна и опиши проверку исправления."
PARCEL = "Опиши, почему нельзя сразу выдать зарегистрированную посылку."


def plan(client, user):
    return client.get("/plan", headers=as_user(user)).get_json()


def item_with(client, user, text):
    return next(i for i in plan(client, user)["items"] if i.get("practice") == text)


def submit(client, user, item_id, answer):
    return client.post(f"/plan/items/{item_id}/practice", json={"answer": answer}, headers=as_user(user))


def test_every_check_matches_a_seed_task():
    """Задания привязаны к тексту practice в seed (зона Codex): переименование не должно молча отключить проверку."""
    seed = SEED_PATH.read_text(encoding="utf-8")
    for text in practice.CHECKS:
        assert json.dumps(text, ensure_ascii=False) in seed


def test_plan_marks_checkable_items(client):
    items = plan(client, "intern-anya")["items"]
    assert any(i["practice_check"] for i in items if i.get("practice") == GIT)
    assert not any(i["practice_check"] for i in items if i.get("practice") and i["practice"] not in practice.CHECKS)


def test_git_task_passes_and_records_event_without_text(client):
    item = item_with(client, "intern-anya", GIT)
    answer = "Создала ветку через git checkout -b 12-readme, сделала коммит, запушила ветку и открыла pull request в main"
    body = submit(client, "intern-anya", item["id"], answer).get_json()
    assert body["passed"] and not body["missing"] and "Готово" in body["text"]
    assert body["source"]["title"] == "Учебный репозиторий — клонирование и ветки"
    [event] = async_runner.run(events.list_events(SYSTEM_ACTOR, type="practice_checked"))
    assert event.payload["passed"] and "checkout" not in json.dumps(event.payload, ensure_ascii=False)


def test_partial_answer_gets_hints_not_answers(client):
    item = item_with(client, "intern-ivan", PARCEL)
    body = submit(client, "intern-ivan", item["id"], "Потому что посылку сначала нужно принять в пункте").get_json()
    assert not body["passed"] and "сначала — «принято»" in body["found"]
    assert len(body["missing"]) == 2 and "готово к выдаче" not in body["text"]
    assert "?;" not in body["text"] and "?." not in body["text"]


def test_ci_task_full_answer(client):
    item = item_with(client, "intern-ivan", CI)
    answer = "Открою первый красный шаг, прочитаю лог с конца, повторю тест локально, исправлю и отправлю новый коммит"
    assert submit(client, "intern-ivan", item["id"], answer).get_json()["passed"]


def test_too_short_answer_is_not_passed(client):
    item = item_with(client, "intern-anya", GIT)
    body = submit(client, "intern-anya", item["id"], "ветка, PR").get_json()
    assert body["passed"] is False and "подробнее" in body["text"]


@pytest.mark.parametrize("user", ["mentor-petr", "intern-kirill", "lead-olga"])
def test_only_owner_intern_can_submit(client, user):
    item = item_with(client, "intern-anya", GIT)
    assert submit(client, user, item["id"], "Создала ветку, коммит, push и pull request").status_code == 404


def test_item_without_check_and_validation(client):
    other = next(i for i in plan(client, "intern-anya")["items"] if not i["practice_check"])
    assert submit(client, "intern-anya", other["id"], "что-то длинное про задание").status_code == 404
    item = item_with(client, "intern-anya", GIT)
    assert submit(client, "intern-anya", item["id"], "").status_code == 422
    assert submit(client, "intern-anya", item["id"], "x" * 2001).status_code == 422


def suggestions(client, mentor="mentor-petr"):
    return client.get("/skills/suggestions", headers=as_user(mentor)).get_json()["suggestions"]


def test_passed_task_becomes_basis_for_mentor(client):
    """Проверка 13.11: наставник видит засчитанное задание основанием поднять уровень — что именно засчитано."""
    item = item_with(client, "intern-anya", GIT)
    assert not [s for s in suggestions(client) if s["topic"] == item["topic"]]
    assert submit(client, "intern-anya", item["id"], "сделала ветку").get_json()["passed"] is False
    assert not [s for s in suggestions(client) if s["topic"] == item["topic"]]  # не засчитано — повода нет

    answer = "создала ветку git checkout -b, сделала коммит, git push и открыла pull request"
    assert submit(client, "intern-anya", item["id"], answer).get_json()["passed"] is True
    [sug] = [s for s in suggestions(client) if s["topic"] == item["topic"]]
    assert sug["basis"].startswith("сдано практическое задание") and "коммит" in sug["basis"]
    assert sug["from_level"] == "novice" and sug["to_level"] == "familiar"
    # повторная сдача не плодит предложения; стажёр предложение не видит; чужой наставник — тоже
    submit(client, "intern-anya", item["id"], answer)
    assert len([s for s in suggestions(client) if s["topic"] == item["topic"]]) == 1
    assert not [s for s in suggestions(client, "mentor-maria") if s["intern_id"] == "intern-anya"]
    kinds = [e.type for e in async_runner.run(events.list_events(SYSTEM_ACTOR, "intern-anya"))]
    assert "practice_passed" in kinds
