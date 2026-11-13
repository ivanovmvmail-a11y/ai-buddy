"""Внедряемость (чекпоинт 2, 13.11): описание API, событие найма, бот в Mattermost."""
import pytest

from app import async_runner
from app.config import settings
from app.mcp_server import checklist
from app.agent.users import DEMO_USERS

from .conftest import as_user, text_reply

TOKEN = "test-service-token"


@pytest.fixture
def tokens(monkeypatch):
    monkeypatch.setattr(settings, "integration_token", TOKEN)
    monkeypatch.setattr(settings, "mattermost_token", "mm-token")
    monkeypatch.setattr(settings, "mattermost_users", "liza.k=intern-liza")


# --- OpenAPI / Swagger -----------------------------------------------------------------------------------

def test_openapi_describes_every_route(client):
    from app.main import create_app
    app = create_app()
    spec = client.get("/openapi.json").get_json()
    rules = {r.rule for r in app.url_map.iter_rules() if r.endpoint != "static"}
    import re
    described = {re.sub(r"\{(\w+)\}", r"<\1>", p) for p in spec["paths"]}
    missing = {re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"<\1>", r) for r in rules} - described
    assert not missing, f"Не описаны в OpenAPI: {missing}"
    assert spec["openapi"].startswith("3.1")


def test_openapi_has_bodies_and_security(client):
    spec = client.get("/openapi.json").get_json()
    chat = spec["paths"]["/chat"]["post"]
    assert chat["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("ChatRequest")
    assert spec["paths"]["/actions"]["post"]["requestBody"]  # DraftIn: tool, params, quick
    assert spec["paths"]["/integrations/hired"]["post"]["security"] == [{"serviceToken": []}]
    assert spec["paths"]["/health"]["get"]["security"] == []
    assert "ChatRequest" in spec["components"]["schemas"] and "HiredIn" in spec["components"]["schemas"]


def test_docs_page_and_spec_are_public(client):
    assert client.get("/openapi.json").status_code == 200  # без X-User-Id
    page = client.get("/docs")
    assert page.status_code == 200 and b"swagger-ui" in page.data


# --- Событие найма ---------------------------------------------------------------------------------------

def hired(client, body, token=TOKEN):
    return client.post("/integrations/hired", json=body, headers={"Authorization": f"Bearer {token}"})


def test_hired_is_off_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "integration_token", "")
    assert hired(client, {"intern_id": "intern-liza", "skills": {}}).status_code == 503


def test_hired_rejects_wrong_token_and_people(client, tokens):
    assert hired(client, {"intern_id": "intern-liza", "skills": {}}, token="wrong").status_code == 401
    # заголовок пользователя ключ службы не заменяет
    res = client.post("/integrations/hired", json={"intern_id": "intern-liza", "skills": {}}, headers=as_user("mentor-maria"))
    assert res.status_code == 401


def test_hired_rebuilds_personal_plan_and_notifies(client, tokens, fresh_onboarding):
    """Лиза: SQL — уверенно, тестирование — нет в карте. Найм прислал: SQL — новичок, тестирование — новичок."""
    res = hired(client, {"intern_id": "intern-liza", "skills": {"sql": "novice", "testing": "novice", "git": "confident"},
                         "strengths": ["Аккуратно пишет тесты"], "growth": ["SQL"]})
    assert res.status_code == 200
    body = res.get_json()
    assert any("SQL" in t for t in body["added"]) and any("Тестирование" in t for t in body["added"])
    assert any("Git" in t for t in body["removed"])  # Git стал «уверенно» — практикум не нужен
    plan = async_runner.run(checklist.get_plan(DEMO_USERS["intern-liza"], "intern-liza"))
    personal = {i.title for i in plan.items if i.kind == "personal"}
    assert {"Практикум: SQL", "Практикум: Тестирование"} <= personal and "Практикум: Git" not in personal
    common = [i for i in plan.items if i.kind == "common"]
    assert common  # общие пункты на месте
    notes = client.get("/reminders", headers=as_user("intern-liza")).get_json()["reminders"]
    assert any("итогам собеседования" in n["text"] for n in notes)


def test_hired_unknown_intern_and_bad_level(client, tokens):
    assert hired(client, {"intern_id": "mentor-petr", "skills": {}}).status_code == 404
    assert hired(client, {"intern_id": "intern-nobody", "skills": {}}).status_code == 404
    assert hired(client, {"intern_id": "intern-liza", "skills": {"git": "гуру"}}).status_code == 422


# --- Mattermost ------------------------------------------------------------------------------------------

def mm(client, **fields):
    return client.post("/integrations/mattermost", data={"token": "mm-token", "user_name": "liza.k", **fields})


def test_mattermost_answers_with_the_same_agent(client, tokens, use_llm):
    llm = use_llm()
    body = mm(client, text="buddy привет", trigger_word="buddy").get_json()
    assert body["response_type"] == "ephemeral" and body["text"].startswith("Привет, Лиза!") and llm.calls == []


def test_mattermost_respects_rights(client, tokens, use_llm):
    use_llm(text_reply("Это данные другого стажёра, показать их я не могу"))
    body = mm(client, text="покажи план Ивана").get_json()
    assert "не могу" in body["text"] or "не раскрыва" in body["text"]


def test_mattermost_drafts_need_confirmation_in_app(client, tokens, use_llm):
    use_llm()
    body = mm(client, text="мне завтра к врачу").get_json()
    assert "Черновик ждёт подтверждения в AI-buddy" in body["text"]
    actions = client.get("/actions", headers=as_user("intern-liza")).get_json()["actions"]
    assert actions and actions[0]["status"] == "pending"  # ничего не отправлено без подтверждения


def test_mattermost_rejects_wrong_token_and_unknown_user(client, tokens):
    assert client.post("/integrations/mattermost", data={"token": "bad", "user_name": "liza.k", "text": "hi"}).status_code == 401
    body = client.post("/integrations/mattermost", data={"token": "mm-token", "user_name": "stranger", "text": "hi"}).get_json()
    assert "Не нашёл тебя" in body["text"]


def test_mattermost_off_without_token(client, monkeypatch):
    monkeypatch.setattr(settings, "mattermost_token", "")
    assert client.post("/integrations/mattermost", data={"token": "", "text": "hi"}).status_code == 503
