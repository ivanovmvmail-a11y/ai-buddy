"""Сквозные тесты T4: HTTP-эндпоинты онбординга и инструменты агента поверх имитаций сервисов (спека 101)."""
import pytest
from .conftest import as_user, text_reply, tool_reply

from app import async_runner
from app.agent import onboarding_tools
from app.agent.users import DEMO_USERS
from app.mcp_server.errors import Conflict


def get(client, url, user="intern-anya"):
    return client.get(url, headers=as_user(user))


def post(client, url, body=None, user="intern-anya"):
    return client.post(url, json=body or {}, headers=as_user(user))


# --- План -------------------------------------------------------------------------------------------

def test_plan_of_self_with_ladder_and_next_step(client):
    body = get(client, "/plan").get_json()
    assert body["intern_id"] == "intern-anya"
    assert body["current_day"] >= 1
    assert [s["title"] for s in body["ladder"]][0] == "Недели 1–2"
    assert body["next_step"]["item"]["owner_role"] == "intern"


def test_plans_differ_between_teams(client):
    anya = {i["title"] for i in get(client, "/plan").get_json()["items"]}
    ivan = {i["title"] for i in get(client, "/plan", "intern-ivan").get_json()["items"]}
    assert anya != ivan and anya & ivan


@pytest.mark.parametrize("user", ["intern-ivan", "mentor-maria", "lead-sergey", "hrbp-elena"])
def test_foreign_plan_is_not_found(client, user):
    res = get(client, "/plan?intern_id=intern-anya", user)
    assert res.status_code == 404
    assert res.get_json() == {"detail": "Не найдено"}


def test_curator_reads_any_plan_but_cannot_mark(client):
    plan = get(client, "/plan?intern_id=intern-ivan", "curator-dmitry").get_json()
    item = next(i for i in plan["items"] if i["owner_role"] == "intern" and not i["resource_id"] and i["stage"] == "week1")
    res = post(client, f"/plan/items/{item['id']}/status", {"status": "done"}, "curator-dmitry")
    assert res.status_code in (403, 404)


@pytest.mark.parametrize("user,expected", [
    ("intern-anya", ["intern-anya"]),
    ("mentor-maria", ["intern-ivan"]),
    ("lead-olga", ["intern-anya"]),
    ("curator-dmitry", ["intern-anya", "intern-ivan"]),
    ("hrbp-elena", []),
])
def test_interns_visible_to_role(client, user, expected):
    assert [u["id"] for u in get(client, "/interns", user).get_json()["interns"]] == expected


def _manual_item(client, user="intern-anya", owner="intern"):
    plan = get(client, f"/plan?intern_id={user}" if user.startswith("intern") else "/plan", user).get_json()
    return next(i for i in plan["items"]
                if i["owner_role"] == owner and not i["resource_id"] and i["status"] != "done" and i["stage"] == "week1")


def test_intern_marks_own_item_done(client):
    item = _manual_item(client)
    res = post(client, f"/plan/items/{item['id']}/status", {"status": "done"})
    assert res.status_code == 200 and res.get_json()["status"] == "done"
    again = next(i for i in get(client, "/plan").get_json()["items"] if i["id"] == item["id"])
    assert again["status"] == "done"


def test_intern_cannot_mark_mentor_item(client):
    item = _manual_item(client, owner="mentor")
    assert post(client, f"/plan/items/{item['id']}/status", {"status": "done"}).status_code == 403


def test_invalid_status_is_422(client):
    item = _manual_item(client)
    assert post(client, f"/plan/items/{item['id']}/status", {"status": "flying"}).status_code == 422


def test_weekly_summary(client):
    body = get(client, "/plan/summary?week=1", "intern-ivan").get_json()
    assert body["intern_id"] == "intern-ivan" and body["week"] == 1
    assert {"closed", "carry_over", "access_granted"} <= body.keys()


# --- Заявка: черновик по кнопке → подтверждение → одобрение наставником ----------------------------

def _team_space_resource(client, user="intern-anya"):
    resources = get(client, "/access/resources", user).get_json()["resources"]
    return next(r for r in resources if r["approver"] == "mentor")


def test_access_request_full_path(client):
    resource = _team_space_resource(client)
    draft = post(client, "/actions", {"tool": "create_access_request",
                                      "params": {"resource_id": resource["id"], "justification": "Изучить репозиторий"}})
    assert draft.status_code == 201
    action = draft.get_json()
    assert action["status"] == "pending" and "чтение" in action["title"]
    assert get(client, "/access/requests").get_json()["requests"] == []  # без подтверждения — ничего

    done = post(client, f"/actions/{action['id']}/confirm").get_json()
    assert done["status"] == "done"
    req = done["result"]["request"]
    assert req["status"] == "pending_approval" and req["approver_id"] == "mentor-petr"

    waiting = next(i for i in get(client, "/plan").get_json()["items"] if i["id"] == req["plan_item_id"])
    assert waiting["status"] == "waiting"

    assert post(client, f"/access/requests/{req['id']}/decide", {"approve": True}).status_code == 403  # стажёр
    assert post(client, f"/access/requests/{req['id']}/decide", {"approve": True}, "mentor-maria").status_code == 404
    decided = post(client, f"/access/requests/{req['id']}/decide", {"approve": True}, "mentor-petr")
    assert decided.get_json()["status"] == "granted"
    closed = next(i for i in get(client, "/plan").get_json()["items"] if i["id"] == req["plan_item_id"])
    assert closed["status"] == "done"


def test_reject_needs_reason(client):
    req = get(client, "/access/requests", "mentor-maria").get_json()["requests"]
    pending = next(r for r in req if r["status"] == "pending_approval")
    assert pending["resource_title"].startswith("Bitbucket")
    assert post(client, f"/access/requests/{pending['id']}/decide", {"approve": False}, "mentor-maria").status_code == 422
    res = post(client, f"/access/requests/{pending['id']}/decide",
               {"approve": False, "reason": "Сначала песочница"}, "mentor-maria")
    assert res.get_json()["status"] == "rejected"


def test_duplicate_request_fails_on_confirm(client):
    resource = _team_space_resource(client)
    params = {"resource_id": resource["id"], "justification": "Нужен доступ"}
    first = post(client, "/actions", {"tool": "create_access_request", "params": params}).get_json()
    second = post(client, "/actions", {"tool": "create_access_request", "params": params}).get_json()
    assert post(client, f"/actions/{first['id']}/confirm").get_json()["status"] == "done"
    failed = post(client, f"/actions/{second['id']}/confirm").get_json()
    assert failed["status"] == "failed" and failed["error"]


@pytest.mark.parametrize("body,status", [
    ({"tool": "nope", "params": {}}, 404),
    ({"tool": "get_plan", "params": {}}, 404),  # read-инструмент черновиком не бывает
    ({"tool": "create_access_request", "params": {"resource_id": "x"}}, 422),
])
def test_draft_errors(client, body, status):
    assert post(client, "/actions", body).status_code == status


def test_mentor_cannot_draft_access_request(client):
    res = post(client, "/actions", {"tool": "create_access_request",
                                    "params": {"resource_id": "jira", "justification": "Нужен доступ"}}, "mentor-petr")
    assert res.status_code == 403


# --- Профиль, напоминания, демо-панель -------------------------------------------------------------

def test_skill_profile_rights(client):
    assert get(client, "/profile/skills").get_json()["skills"]
    assert get(client, "/profile/skills?intern_id=intern-anya", "mentor-petr").status_code == 200
    assert get(client, "/profile/skills?intern_id=intern-anya", "curator-dmitry").status_code == 404


def test_mentor_sets_skill_level(client):
    body = {"intern_id": "intern-anya", "topic": "git", "level": "familiar"}
    res = post(client, "/profile/skills", body, "mentor-petr")
    assert res.status_code == 200 and res.get_json()["skills"]["git"] == "familiar"
    assert get(client, "/profile/skills").get_json()["skills"]["git"] == "familiar"
    new_topic = post(client, "/profile/skills", {**body, "topic": "ci", "level": "novice"}, "mentor-petr")
    assert new_topic.get_json()["skills"]["ci"] == "novice"


@pytest.mark.parametrize("user, code", [
    ("intern-anya", 403),      # стажёр сам себе уровень не ставит
    ("mentor-maria", 404),     # чужой наставник стажёра не видит
    ("curator-dmitry", 404),   # куратору карта навыков закрыта
])
def test_only_own_mentor_sets_skill_level(client, user, code):
    res = post(client, "/profile/skills", {"intern_id": "intern-anya", "topic": "git", "level": "confident"}, user)
    assert res.status_code == code
    assert get(client, "/profile/skills").get_json()["skills"]["git"] == "novice"


def test_skill_level_validation(client):
    res = post(client, "/profile/skills", {"intern_id": "intern-anya", "topic": "git", "level": "expert"}, "mentor-petr")
    assert res.status_code == 422


def test_next_day_creates_reminders_then_snooze_and_done(client):
    days = post(client, "/demo/next-day", {}, "intern-ivan").get_json()["days"]
    assert days["intern-ivan"] >= 2
    reminders = get(client, "/reminders", "intern-ivan").get_json()["reminders"]
    assert reminders
    first, *rest = reminders
    snoozed = post(client, f"/reminders/{first['id']}/snooze", {"days": 1}, "intern-ivan").get_json()
    assert snoozed["status"] == "snoozed"
    if rest:
        assert post(client, f"/reminders/{rest[0]['id']}/done", {}, "intern-ivan").get_json()["status"] == "done"
    assert post(client, f"/reminders/{first['id']}/done", {}, "intern-anya").status_code == 404


def test_reset_returns_start_state(client):
    item = _manual_item(client)
    post(client, f"/plan/items/{item['id']}/status", {"status": "done"})
    assert post(client, "/demo/reset").get_json() == {"status": "reset"}
    again = next(i for i in get(client, "/plan").get_json()["items"] if i["id"] == item["id"])
    assert again["status"] != "done"


# --- Агент ----------------------------------------------------------------------------------------

def ask(client, text, user="intern-anya"):
    return client.post("/chat", json={"messages": [{"role": "user", "content": text}]}, headers=as_user(user))


def test_prompt_has_plan_context_for_intern(client, use_llm):
    llm = use_llm(text_reply("ok"))
    ask(client, "что дальше?")
    system = llm.calls[0][0][0].content
    assert "Следующий шаг" in system and "Уровень по темам" in system
    ask(client, "что дальше?", "hrbp-elena")
    assert "Следующий шаг" not in llm.calls[1][0][0].content


def test_tools_shown_by_role(client, use_llm):
    llm = use_llm(text_reply("ok"))
    ask(client, "?", "intern-anya")
    ask(client, "?", "hrbp-elena")
    intern_tools = {t.name for t in llm.calls[0][1]}
    hr_tools = {t.name for t in llm.calls[1][1]}
    assert {"get_plan", "create_access_request", "get_skill_profile"} <= intern_tools
    assert "decide_access_request" not in intern_tools and "set_skill_level" not in intern_tools
    assert not hr_tools & {"get_plan", "create_access_request", "get_skill_profile"}


def test_agent_reads_plan_through_tool(client, use_llm):
    llm = use_llm(tool_reply("get_plan"), text_reply("Твой следующий шаг…"))
    res = ask(client, "что мне делать?")
    assert res.status_code == 200
    tool_msg = llm.calls[1][0][-1]
    assert tool_msg.role == "tool" and "next_step" in tool_msg.content


def test_agent_foreign_plan_is_forbidden_without_details(client, use_llm):
    llm = use_llm(tool_reply("get_plan", {"intern_id": "intern-ivan"}), text_reply("Нет доступа"))
    ask(client, "покажи план Ивана")
    content = llm.calls[1][0][-1].content
    assert "forbidden" in content and "Авито Доставка" not in content


def test_agent_drafts_access_request(client, use_llm):
    use_llm(tool_reply("create_access_request", {"resource_id": "jira", "justification": "Задачи команды"}),
            text_reply("Подготовил черновик"))
    body = ask(client, "закажи доступ в Jira").get_json()
    assert len(body["actions"]) == 1 and body["actions"][0]["status"] == "pending"
    assert get(client, "/access/requests").get_json()["requests"] == []


def test_domain_error_mapping():
    assert onboarding_tools.domain_error(Conflict("уже есть"))["error"] == "conflict"
    plan = async_runner.run(onboarding_tools.get_plan(DEMO_USERS["hrbp-elena"], onboarding_tools.PlanArgs()))
    assert plan["error"] == "forbidden"


def test_resource_titles_from_seed():
    assert onboarding_tools.resource_titles()


def _call(fn, user, args):
    return async_runner.run(fn(DEMO_USERS[user], args))


def test_tool_handlers_directly(fresh_onboarding):
    t = onboarding_tools
    assert _call(t.list_access_resources, "intern-anya", t.NoArgs())["resources"]
    assert _call(t.get_skill_profile, "intern-ivan", t.PlanArgs())["skills"]
    reqs = _call(t.list_access_requests, "mentor-maria", t.RequestsArgs(intern_id="intern-ivan"))["requests"]
    pending = next(r for r in reqs if r["status"] == "pending_approval")
    decided = _call(t.decide_access_request, "mentor-maria", t.DecideArgs(request_id=pending["id"], approve=True))
    assert decided["request"]["status"] == "granted"
    plan = _call(t.get_plan, "intern-anya", t.PlanArgs())
    manual = next(i for i in plan["items"] if i["owner_role"] == "intern" and not i["resource_id"] and i["status"] != "done")
    updated = _call(t.set_plan_item_status, "intern-anya", t.StatusArgs(item_id=manual["id"], status="done"))
    assert updated["item"]["status"] == "done"
    created = _call(t.create_access_request, "intern-anya",
                    t.RequestArgs(resource_id=plan["items"][1]["resource_id"] or "jira", justification="Нужен доступ"))
    assert created.get("status") == "created" or created.get("error") == "conflict"
    assert _call(t.list_access_resources, "mentor-petr", t.NoArgs())["error"] == "forbidden"


def test_plan_context_mentions_waiting_and_skips_on_error(fresh_onboarding, monkeypatch):
    ctx = async_runner.run(onboarding_tools.plan_context(DEMO_USERS["intern-ivan"]))
    assert "Ждёт другого человека" in ctx

    async def broken(*a, **k):
        raise Conflict()
    monkeypatch.setattr(onboarding_tools.checklist, "get_plan", broken)
    assert async_runner.run(onboarding_tools.plan_context(DEMO_USERS["intern-anya"])) == ""


def test_invalid_args_mapping():
    from pydantic import BaseModel, ValidationError

    class M(BaseModel):
        x: int
    try:
        M.model_validate({"x": "a"})
    except ValidationError as exc:
        assert onboarding_tools.domain_error(exc)["error"] == "invalid_arguments"


def test_tool_schemas_have_no_nullable_anyof(agent):
    """GigaChat отклоняет anyOf с null в параметрах (живая проверка T4)."""
    for tool in agent.registry.tools.values():
        for name, prop in tool.spec().parameters.get("properties", {}).items():
            assert "anyOf" not in prop, (tool.name, name)
            assert "type" in prop or "enum" in prop, (tool.name, name)
