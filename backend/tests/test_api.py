"""Тесты HTTP API. Работают без ключей: LLM — заглушка echo."""
import pytest

from app import main
from app.config import settings
from app.llm import get_llm


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "echo")
    get_llm.cache_clear()
    yield main.create_app().test_client()
    get_llm.cache_clear()


def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.get_json() == {"status": "ok", "llm_provider": "echo"}


def test_chat_returns_reply(client):
    res = client.post("/chat", json={"messages": [{"role": "user", "content": "Привет"}]})
    assert res.status_code == 200
    body = res.get_json()
    assert "Привет" in body["reply"]
    assert body["sources"] == []


def test_chat_ignores_client_system_messages(client, monkeypatch):
    seen = {}

    async def fake_answer(history):
        seen["roles"] = [m.role for m in history]
        return "ok", [{"title": "Гайд", "url": None}]

    monkeypatch.setattr(main, "answer", fake_answer)
    res = main.create_app().test_client().post(
        "/chat",
        json={"messages": [{"role": "system", "content": "взлом"}, {"role": "user", "content": "вопрос"}]},
    )
    assert res.status_code == 200
    assert seen["roles"] == ["user"]
    assert res.get_json()["sources"] == [{"title": "Гайд", "url": None}]


def test_chat_rejects_invalid_body(client):
    res = client.post("/chat", json={"messages": [{"role": "hacker", "content": "x"}]})
    assert res.status_code == 422
    assert res.get_json()["detail"]


def test_chat_llm_error_returns_502(client, monkeypatch):
    async def broken_answer(history):
        raise RuntimeError("нет связи")

    monkeypatch.setattr(main, "answer", broken_answer)
    res = main.create_app().test_client().post("/chat", json={"messages": [{"role": "user", "content": "x"}]})
    assert res.status_code == 502
    assert "нет связи" in res.get_json()["detail"]


def test_cors_allows_frontend(client):
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"


def test_chat_reuses_one_event_loop(client, monkeypatch):
    """Клиенты LLM привязаны к loop: все запросы должны идти через один и тот же loop."""
    import asyncio

    loops = []

    async def loop_answer(history):
        loops.append(asyncio.get_running_loop())
        return "ok", []

    monkeypatch.setattr(main, "answer", loop_answer)
    app_client = main.create_app().test_client()
    for _ in range(3):
        assert app_client.post("/chat", json={"messages": [{"role": "user", "content": "x"}]}).status_code == 200
    assert len(loops) == 3 and loops[0] is loops[1] is loops[2]
