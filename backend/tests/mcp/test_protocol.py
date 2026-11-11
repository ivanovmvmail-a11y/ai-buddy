"""Официальный MCP-клиент ↔ FastMCP по memory transport и stdio, без сети/ключей."""
import asyncio
from datetime import timedelta
from pathlib import Path
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session
import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, clock
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.server import mcp

run = async_runner.run
BACKEND = Path(__file__).resolve().parents[2]
ANYA = "intern-anya"
CALLS = {
    "get_plan": {"intern_id": ANYA},
    "set_item_status": {"item_id": "anya.w1.notes", "status": "done"},
    "list_resources": {},
    "create_request": {"resource_id": "jira", "level": "read", "justification": "Демо-задача"},
    "list_requests": {},
    "decide_request": {"request_id": "REQ-1001", "approve": True},
    "get_skill_profile": {"intern_id": ANYA},
    "list_reminders": {},
}


def text(result):
    return "\n".join(block.text for block in result.content if block.type == "text")


def data(result):
    assert not result.isError, text(result)
    assert result.structuredContent is not None
    return result.structuredContent


def test_catalog_has_exactly_eight_tools_and_required_explicit_user_id(store):
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            tools = (await client.list_tools()).tools
            assert {tool.name for tool in tools} == set(CALLS)
            for tool in tools:
                assert "user_id" in tool.inputSchema["required"]
                assert tool.inputSchema["properties"]["user_id"]["type"] == "string"
                assert not {"actor", "role", "team"} & set(tool.inputSchema["properties"])
                assert tool.outputSchema
            for name in ("SYSTEM_ACTOR", "cron_tick", "log_event", "set_skill_level", "reset_demo"):
                assert (await client.call_tool(name, {"user_id": ANYA})).isError
    run(exercise())


def test_eight_tools_roundtrip_and_persist_service_changes(store):
    async def exercise():
        await clock.cron_tick(SYSTEM_ACTOR)  # Только подготовка теста; этого инструмента в MCP нет.
        async with create_connected_server_and_client_session(mcp) as client:
            plan = data(await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": ANYA}))
            assert plan["current_day"] == 2 and plan["next_step"]
            resources = data(await client.call_tool("list_resources", {"user_id": ANYA}))["result"]
            assert "bitbucket-platform" in {resource["id"] for resource in resources}
            assert "bitbucket-delivery" not in {resource["id"] for resource in resources}
            updated = data(await client.call_tool("set_item_status", {"user_id": ANYA, **CALLS["set_item_status"]}))
            assert updated["status"] == "done" and updated["updated_by"] == ANYA
            request = data(await client.call_tool("create_request", {"user_id": ANYA, "resource_id": "bitbucket-platform",
                                                                        "level": "read", "justification": "Демо-задача"}))
            assert request["status"] == "pending_approval"
            listed = data(await client.call_tool("list_requests", {"user_id": "mentor-petr", "intern_id": ANYA}))["result"]
            assert [entry["id"] for entry in listed] == [request["id"]]
            decided = data(await client.call_tool("decide_request", {"user_id": "mentor-petr", "request_id": request["id"], "approve": True}))
            assert decided["status"] == "granted"
            profile = data(await client.call_tool("get_skill_profile", {"user_id": ANYA, "intern_id": ANYA}))
            assert profile["skills"]["git"] == "novice"
            reminders = data(await client.call_tool("list_reminders", {"user_id": "intern-ivan"}))["result"]
            assert reminders and all(reminder["user_id"] == "intern-ivan" for reminder in reminders)
            plan = data(await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": ANYA}))
            assert next(item for item in plan["items"] if item["id"] == request["plan_item_id"])["status"] == "done"
    run(exercise())


@pytest.mark.parametrize("user_id", ["not-a-user", "system", "", None, {"id": ANYA, "role": "system"}])
def test_every_tool_rejects_unknown_or_malformed_user_without_changes(store, snapshot, user_id):
    before = snapshot()
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            for name, arguments in CALLS.items():
                result = await client.call_tool(name, {"user_id": user_id, **arguments})
                assert result.isError, name
                if isinstance(user_id, str):
                    assert "Неизвестный пользователь" in text(result)
            for name, arguments in CALLS.items():
                assert (await client.call_tool(name, arguments)).isError  # Нет пользователя по умолчанию.
    run(exercise())
    assert snapshot() == before


@pytest.mark.parametrize("name,foreign,missing", [
    ("get_plan", {"intern_id": "intern-ivan"}, {"intern_id": "missing"}),
    ("set_item_status", {"item_id": "ivan.w1.notes", "status": "done"}, {"item_id": "missing", "status": "done"}),
    ("create_request", {"resource_id": "bitbucket-delivery", "level": "read", "justification": "Демо"},
                       {"resource_id": "missing", "level": "read", "justification": "Демо"}),
    ("list_requests", {"intern_id": "intern-ivan"}, {"intern_id": "missing"}),
    ("decide_request", {"request_id": "REQ-1001", "approve": True}, {"request_id": "missing", "approve": True}),
    ("get_skill_profile", {"intern_id": "intern-ivan"}, {"intern_id": "missing"}),
])
def test_foreign_and_missing_objects_have_identical_not_found_results(store, snapshot, name, foreign, missing):
    before = snapshot()
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            denied = await client.call_tool(name, {"user_id": ANYA, **foreign})
            absent = await client.call_tool(name, {"user_id": ANYA, **missing})
            assert denied.isError and absent.isError
            assert denied == absent
            assert "Не найдено" in text(denied)
            assert "intern-ivan" not in text(denied) and "Авито Доставка" not in text(denied)
    run(exercise())
    assert snapshot() == before


@pytest.mark.parametrize("user_id", DEMO_USERS)
def test_protocol_uses_service_permissions_for_all_eight_demo_users(store, user_id):
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            plan = await client.call_tool("get_plan", {"user_id": user_id, "intern_id": ANYA})
            assert (not plan.isError) == (user_id in {ANYA, "mentor-petr", "lead-olga", "curator-dmitry"})
            profile = await client.call_tool("get_skill_profile", {"user_id": user_id, "intern_id": ANYA})
            assert (not profile.isError) == (user_id in {ANYA, "mentor-petr"})
    run(exercise())


def test_validation_conflict_and_forbidden_are_tool_errors(store):
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            invalid = await client.call_tool("create_request", {"user_id": ANYA, **CALLS["create_request"], "justification": " "})
            assert invalid.isError and "Некорректные параметры" in text(invalid)
            data(await client.call_tool("create_request", {"user_id": ANYA, **CALLS["create_request"]}))
            duplicate = await client.call_tool("create_request", {"user_id": ANYA, **CALLS["create_request"]})
            assert duplicate.isError and "уже существует" in text(duplicate)
            forbidden = await client.call_tool("list_resources", {"user_id": "mentor-petr"})
            assert forbidden.isError and "Действие запрещено" in text(forbidden)
            for approve in (1, "true"):
                assert (await client.call_tool("decide_request", {"user_id": "mentor-maria", "request_id": "REQ-1001", "approve": approve})).isError
    run(exercise())


def test_unexpected_failure_is_sanitized_and_session_stays_usable(store, monkeypatch, caplog):
    async def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_CONNECTION_DETAILS")
    monkeypatch.setattr(checklist, "get_plan", fail)
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            result = await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": ANYA})
            assert result.isError and "Сервис временно недоступен" in text(result)
            assert "PRIVATE_CONNECTION_DETAILS" not in text(result)
            data(await client.call_tool("get_skill_profile", {"user_id": ANYA, "intern_id": ANYA}))
    run(exercise())
    assert "RuntimeError" in caplog.text and "PRIVATE_CONNECTION_DETAILS" not in caplog.text


def test_server_closes_store_on_shared_event_loop(store, monkeypatch):
    closed = []
    close = store.close
    async def tracked_close():
        closed.append(asyncio.get_running_loop())
        await close()
    monkeypatch.setattr(store, "close", tracked_close)
    async def exercise():
        async with create_connected_server_and_client_session(mcp) as client:
            await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": ANYA})
        assert closed == [asyncio.get_running_loop()]
    run(exercise())


def test_stdio_module_entrypoint_with_official_client(tmp_path):
    async def exercise():
        parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server.server"],
            cwd=str(BACKEND), env={"DATABASE_URL": "", "LLM_PROVIDER": "echo", "PYTHONUTF8": "1"})
        with (tmp_path / "mcp-stderr.log").open("w", encoding="utf-8") as stderr:
            async with stdio_client(parameters, errlog=stderr) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as client:
                    initialized = await client.initialize()
                    assert initialized.serverInfo.name == "AI-buddy onboarding"
                    assert {tool.name for tool in (await client.list_tools()).tools} == set(CALLS)
                    plan = data(await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": ANYA}))
                    assert plan["current_day"] == 2
                    denied = await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": "intern-ivan"})
                    absent = await client.call_tool("get_plan", {"user_id": ANYA, "intern_id": "missing"})
                    assert denied.isError and denied == absent
    run(exercise())
