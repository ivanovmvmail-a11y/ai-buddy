"""Хранилище действий: атомарное подтверждение (аудит D1), сброс демо, интерфейс для PostgreSQL (SPEC 9)."""
from concurrent.futures import ThreadPoolExecutor

from .conftest import as_user

from app import async_runner
from app.agent.actions import InMemoryActionStore

DRAFT = {"tool": "create_access_request",
         "params": {"resource_id": "jira", "level": "read", "justification": "Стажировка: учебный Jira"}}


def draft(client, user="intern-anya"):
    res = client.post("/actions", json=DRAFT, headers=as_user(user))
    assert res.status_code == 201
    return res.get_json()["id"]


def test_parallel_confirmations_execute_once_and_action_stays_done(client):
    action_id = draft(client)
    with ThreadPoolExecutor(max_workers=6) as pool:
        codes = list(pool.map(lambda _: client.post(f"/actions/{action_id}/confirm", headers=as_user("intern-anya")).status_code,
                              range(6)))
    assert sorted(codes) == [200, 409, 409, 409, 409, 409]
    [action] = client.get("/actions", headers=as_user("intern-anya")).get_json()["actions"]
    assert action["status"] == "done"
    requests = client.get("/access/requests", headers=as_user("intern-anya")).get_json()["requests"]
    assert sum(r["resource_id"] == "jira" for r in requests) == 1


def test_foreign_or_finished_draft_cannot_be_claimed(client):
    action_id = draft(client)
    assert client.post(f"/actions/{action_id}/confirm", headers=as_user("intern-ivan")).status_code == 404
    assert client.post(f"/actions/{action_id}/cancel", headers=as_user("intern-anya")).status_code == 200
    assert client.post(f"/actions/{action_id}/cancel", headers=as_user("intern-anya")).status_code == 409
    assert client.post(f"/actions/{action_id}/confirm", headers=as_user("intern-anya")).status_code == 409


def test_demo_reset_clears_drafts(client):
    draft(client)
    assert client.get("/actions", headers=as_user("intern-anya")).get_json()["actions"]
    assert client.post("/demo/reset", headers=as_user("intern-anya")).status_code == 200
    assert client.get("/actions", headers=as_user("intern-anya")).get_json()["actions"] == []


def test_forbidden_on_confirm_releases_the_draft(client, monkeypatch):
    from app.agent import service

    action_id = draft(client)
    monkeypatch.setattr(service, "check_access", lambda *a: False)
    assert client.post(f"/actions/{action_id}/confirm", headers=as_user("intern-anya")).status_code == 403
    [action] = client.get("/actions", headers=as_user("intern-anya")).get_json()["actions"]
    assert action["status"] == "pending"  # не застрял в «running»


def test_in_memory_store_returns_copies():
    store = InMemoryActionStore()
    action = async_runner.run(store.create(user_id="u", tool="t", title="T", params={"a": 1}))
    action.params["a"] = 2  # изменение копии без save не попадает в хранилище
    assert async_runner.run(store.get(action.id)).params == {"a": 1}
    assert async_runner.run(store.claim(action.id, "other")) is None
    assert async_runner.run(store.claim(action.id, "u")).status == "running"
    assert async_runner.run(store.claim(action.id, "u")) is None
