"""Шлюз агента к сервисам (app/agent/services.py): в режиме MCP агент ходит к сервисам по протоколу MCP, и результат
тот же, что при прямом вызове. Весь набор тестов дополнительно гоняется с AGENT_SERVICES=mcp в CI."""
import pytest

from .conftest import text_reply
from .test_agent import run_agent

from app import async_runner
from app.agent import services
from app.agent.users import DEMO_USERS
from app.config import settings
from app.mcp_server.errors import Conflict, Forbidden, NotFound

ANYA, IVAN, PETR = DEMO_USERS["intern-anya"], DEMO_USERS["intern-ivan"], DEMO_USERS["mentor-petr"]


@pytest.fixture
def via_mcp(monkeypatch, fresh_onboarding):
    monkeypatch.setattr(settings, "agent_services", "mcp")
    calls = []
    real = services.call_tool

    async def spy(user, tool, arguments, result_type):
        calls.append((user.id, tool))
        return await real(user, tool, arguments, result_type)
    monkeypatch.setattr(services, "call_tool", spy)
    return calls


def test_mode_switch(monkeypatch):
    monkeypatch.setattr(settings, "agent_services", "direct")
    assert services.mode() == "direct"
    monkeypatch.setattr(settings, "agent_services", " MCP ")
    assert services.mode() == "mcp"


def test_same_results_direct_and_mcp(monkeypatch, fresh_onboarding):
    async def read_all():
        plan = await services.get_plan(ANYA, ANYA.id)
        profile = await services.get_skill_profile(PETR, ANYA.id)
        resources = await services.list_resources(ANYA)
        requests = await services.list_requests(IVAN, None)
        return plan, profile, resources, requests

    monkeypatch.setattr(settings, "agent_services", "direct")
    direct = async_runner.run(read_all())
    monkeypatch.setattr(settings, "agent_services", "mcp")
    over_mcp = async_runner.run(read_all())
    assert over_mcp == direct


def test_mcp_errors_become_domain_errors(via_mcp):
    with pytest.raises(NotFound):  # чужой план — как несуществующий
        async_runner.run(services.get_plan(ANYA, IVAN.id))
    with pytest.raises(Forbidden):  # пункт наставника стажёр не отмечает
        async_runner.run(services.set_item_status(ANYA, "anya.w1.channels", "done", None))
    with pytest.raises(services.InvalidArguments):
        async_runner.run(services.create_request(ANYA, "jira", "superuser", "нужно для задачи"))


def test_error_text_mapping():
    assert isinstance(services._error("Error executing tool x: Не найдено"), NotFound)
    assert isinstance(services._error("Общий пункт нельзя убрать"), Forbidden)
    assert isinstance(services._error("Сервис временно недоступен"), RuntimeError)
    assert isinstance(services._error("Некорректные параметры"), services.InvalidArguments)
    conflict = services._error("Error executing tool create_request: Заявка уже есть")
    assert isinstance(conflict, Conflict) and str(conflict) == "Заявка уже есть"


def test_agent_chat_goes_through_mcp(via_mcp, agent, use_llm):
    use_llm(text_reply("не нужна"))
    reply = run_agent(agent, "intern-anya", text="что мне делать дальше?").reply
    assert "Следующий шаг" in reply
    assert ("intern-anya", "get_plan") in via_mcp


def test_refusal_over_mcp_is_still_refusal(via_mcp, agent, use_llm):
    use_llm(text_reply("не нужна"))
    result = run_agent(agent, "mentor-petr", text="что у Ивана зависло?")
    assert result.refused and "нет доступа" in result.reply
