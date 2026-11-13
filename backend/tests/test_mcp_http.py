"""MCP по сети (Streamable HTTP, спека 005): настоящий HTTP-сервер на свободном порту, агент — HTTP-клиент."""
import asyncio
import socket

import httpx
import pytest

pytest.importorskip("mcp")
import uvicorn  # noqa: E402

from app import async_runner  # noqa: E402
from app.agent import services  # noqa: E402
from app.agent.users import DEMO_USERS  # noqa: E402
from app.config import settings  # noqa: E402
from app.mcp_server.errors import NotFound  # noqa: E402
from app.mcp_server.http_server import create_app  # noqa: E402

from .conftest import text_reply  # noqa: E402
from .test_agent import run_agent  # noqa: E402

TOKEN = "test-token"
ANYA, IVAN, PETR = DEMO_USERS["intern-anya"], DEMO_USERS["intern-ivan"], DEMO_USERS["mentor-petr"]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def mcp_http(fresh_onboarding):
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(TOKEN), host="127.0.0.1", port=port, log_level="warning",
                                           lifespan="on"))
    loop = async_runner._get_loop()
    future = asyncio.run_coroutine_threadsafe(server.serve(), loop)

    async def started():
        while not server.started:
            await asyncio.sleep(0.02)
    async_runner.run(started(), timeout=10)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    future.result(10)


@pytest.fixture
def via_http(mcp_http, monkeypatch):
    monkeypatch.setattr(settings, "agent_services", "mcp")
    monkeypatch.setattr(settings, "mcp_url", f"{mcp_http}/mcp")
    monkeypatch.setattr(settings, "mcp_service_token", TOKEN)
    return mcp_http


def test_server_needs_token():
    with pytest.raises(ValueError):
        create_app("")


def test_http_rejects_wrong_token_and_unknown_user(mcp_http):
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    accept = {"Accept": "application/json, text/event-stream"}
    assert httpx.get(f"{mcp_http}/health").status_code == 200
    assert httpx.post(f"{mcp_http}/mcp", json=body, headers=accept).status_code == 401
    assert httpx.post(f"{mcp_http}/mcp", json=body, headers={**accept, "Authorization": "Bearer wrong",
                                                              "X-AI-Buddy-User": "intern-anya"}).status_code == 401
    assert httpx.post(f"{mcp_http}/mcp", json=body, headers={**accept, "Authorization": f"Bearer {TOKEN}",
                                                              "X-AI-Buddy-User": "hacker"}).status_code == 403


def test_transport_name(via_http, monkeypatch):
    assert services.transport() == "mcp-http"
    monkeypatch.setattr(settings, "mcp_url", "")
    assert services.transport() == "mcp-memory"
    monkeypatch.setattr(settings, "agent_services", "direct")
    assert services.transport() == "direct"


def test_same_results_direct_and_http(via_http, monkeypatch):
    async def read_all():
        return (await services.get_plan(ANYA, ANYA.id), await services.get_skill_profile(PETR, ANYA.id),
                await services.list_resources(ANYA), await services.list_requests(IVAN, None))

    over_http = async_runner.run(read_all())
    monkeypatch.setattr(settings, "agent_services", "direct")
    assert over_http == async_runner.run(read_all())


def test_http_user_comes_from_header_not_model(via_http):
    with pytest.raises(NotFound):  # Аня по сети не видит план Ивана — права проверяет сервер
        async_runner.run(services.get_plan(ANYA, IVAN.id))


def test_agent_chat_over_http(via_http, agent, use_llm):
    use_llm(text_reply("не нужна"))
    assert "Следующий шаг" in run_agent(agent, "intern-anya", text="что мне делать дальше?").reply
    refused = run_agent(agent, "mentor-petr", text="что у Ивана зависло?")
    assert refused.refused and "нет доступа" in refused.reply
