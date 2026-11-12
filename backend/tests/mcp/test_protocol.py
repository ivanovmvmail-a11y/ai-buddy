"""MCP: личность привязана к запуску, официальный клиент ↔ memory/stdio."""
import asyncio
from datetime import timedelta
import os
from pathlib import Path
import subprocess
import sys

import pytest

pytest.importorskip("mcp", reason="Для протокольных тестов: uv sync --extra mcp")
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session as connected

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, clock, server
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.models import Reminder

run = async_runner.run
BACKEND = Path(__file__).resolve().parents[2]
ANYA = "intern-anya"
NAMES = {"get_plan", "set_item_status", "list_resources", "create_request", "list_requests",
         "decide_request", "get_skill_profile", "list_reminders"}


def text(result):
    return "\n".join(block.text for block in result.content if block.type == "text")


def data(result):
    assert not result.isError, text(result)
    assert result.structuredContent is not None
    return result.structuredContent


def test_catalog_has_no_user_argument_and_marks_mutations(store):
    async def exercise():
        async with connected(server.create_server(ANYA)) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            assert {name for name in tools if not name.startswith(("mentor_", "absence_", "self_check_"))} == NAMES
            for tool in tools.values():
                assert not {"user_id", "actor", "role", "team"} & set(tool.inputSchema.get("properties", {}))
                assert tool.outputSchema
            for name in ("set_item_status", "decide_request"):
                assert tools[name].annotations.destructiveHint is True
                assert tools[name].annotations.readOnlyHint is False
            assert tools["create_request"].annotations.destructiveHint is False
            assert tools["create_request"].annotations.idempotentHint is False
            for name in ("SYSTEM_ACTOR", "cron_tick", "log_event", "set_skill_level", "reset_demo"):
                assert (await client.call_tool(name, {})).isError
    run(exercise())


def test_eight_tools_roundtrip_with_separate_intern_and_mentor_servers(store):
    async def exercise():
        await clock.cron_tick(SYSTEM_ACTOR)
        async with connected(server.create_server(ANYA)) as client:
            plan = data(await client.call_tool("get_plan", {"intern_id": ANYA}))
            assert plan["current_day"] == 2 and plan["next_step"]
            resources = data(await client.call_tool("list_resources", {}))["result"]
            assert "bitbucket-platform" in {resource["id"] for resource in resources}
            assert "bitbucket-delivery" not in {resource["id"] for resource in resources}
            updated = data(await client.call_tool("set_item_status", {"item_id": "anya.w1.notes", "status": "done"}))
            assert updated["status"] == "done" and updated["updated_by"] == ANYA
            request = data(await client.call_tool("create_request", {"resource_id": "bitbucket-platform",
                                                       "level": "read", "justification": "Демо-задача"}))
            assert request["status"] == "pending_approval" and request["intern_id"] == ANYA
            assert (await client.call_tool("decide_request", {"request_id": request["id"], "approve": True})).isError
            profile = data(await client.call_tool("get_skill_profile", {"intern_id": ANYA}))
            assert profile["skills"]["git"] == "novice"
        async with connected(server.create_server("mentor-petr")) as mentor:
            listed = data(await mentor.call_tool("list_requests", {"intern_id": ANYA}))["result"]
            assert [entry["id"] for entry in listed] == [request["id"]]
            decided = data(await mentor.call_tool("decide_request", {"request_id": request["id"], "approve": True}))
            assert decided["status"] == "granted"
        async with connected(server.create_server("intern-ivan")) as ivan:
            reminders = data(await ivan.call_tool("list_reminders", {}))["result"]
            assert reminders and all(r["user_id"] == "intern-ivan" and r["status"] == "active" for r in reminders)
        async with connected(server.create_server(ANYA)) as client:
            plan = data(await client.call_tool("get_plan", {"intern_id": ANYA}))
            assert next(item for item in plan["items"] if item["id"] == request["plan_item_id"])["status"] == "done"
    run(exercise())


def test_client_cannot_switch_to_mentor_and_approve_own_request(store, monkeypatch):
    async def exercise():
        instance = server.create_server(ANYA)
        # Даже изменение окружения после создания сервера не меняет связанную личность.
        monkeypatch.setenv("MCP_USER_ID", "mentor-petr")
        async with connected(instance) as client:
            request = data(await client.call_tool("create_request", {"resource_id": "bitbucket-platform",
                                                         "level": "read", "justification": "Демо"}))
            for forged in ({"user_id": "mentor-petr"}, {"actor": {"id": "mentor-petr"}, "role": "mentor"}):
                result = await client.call_tool("decide_request", {"request_id": request["id"], "approve": True, **forged})
                assert result.isError
            listed = data(await client.call_tool("list_requests", {}))["result"]
            assert listed[0]["status"] == "pending_approval"
            denied = await client.call_tool("get_plan", {"intern_id": "intern-ivan", "user_id": "mentor-maria"})
            assert denied.isError and "Не найдено" in text(denied)
    run(exercise())


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
        async with connected(server.create_server(ANYA)) as client:
            denied = await client.call_tool(name, foreign)
            absent = await client.call_tool(name, missing)
            assert denied.isError and denied == absent
            assert "Не найдено" in text(denied)
            assert "intern-ivan" not in text(denied) and "Авито Доставка" not in text(denied)
    run(exercise())
    assert snapshot() == before


@pytest.mark.parametrize("user_id", DEMO_USERS)
def test_protocol_uses_service_permissions_for_all_eight_demo_users(store, user_id):
    async def exercise():
        async with connected(server.create_server(user_id)) as client:
            plan = await client.call_tool("get_plan", {"intern_id": ANYA})
            assert (not plan.isError) == (user_id in {ANYA, "mentor-petr", "lead-olga", "curator-dmitry"})
            profile = await client.call_tool("get_skill_profile", {"intern_id": ANYA})
            assert (not profile.isError) == (user_id in {ANYA, "mentor-petr"})
    run(exercise())


def test_list_reminders_only_returns_active_personal_records(store, edit):
    def prepare(state):
        for name, owner, status in (("active", ANYA, "active"), ("snoozed", ANYA, "snoozed"),
                                    ("done", ANYA, "done"), ("foreign", "intern-ivan", "active")):
            state.reminders[name] = Reminder(id=name, user_id=owner, status=status, text="Демо", created_day=2)
    edit(prepare)
    async def exercise():
        async with connected(server.create_server(ANYA)) as client:
            assert [r["id"] for r in data(await client.call_tool("list_reminders", {}))["result"]] == ["active"]
    run(exercise())


def test_validation_conflict_and_forbidden_are_tool_errors(store):
    async def exercise():
        async with connected(server.create_server(ANYA)) as client:
            args = {"resource_id": "jira", "level": "read", "justification": "Демо"}
            invalid = await client.call_tool("create_request", {**args, "justification": " "})
            assert invalid.isError and "Некорректные параметры" in text(invalid)
            data(await client.call_tool("create_request", args))
            duplicate = await client.call_tool("create_request", args)
            assert duplicate.isError and "уже существует" in text(duplicate)
        async with connected(server.create_server("mentor-maria")) as client:
            forbidden = await client.call_tool("list_resources", {})
            assert forbidden.isError and "Действие запрещено" in text(forbidden)
            for approve in (1, "true"):
                assert (await client.call_tool("decide_request", {"request_id": "REQ-1001", "approve": approve})).isError
    run(exercise())


def test_unexpected_failure_is_sanitized_and_session_stays_usable(store, monkeypatch, caplog):
    async def fail(*args, **kwargs):
        raise RuntimeError("PRIVATE_CONNECTION_DETAILS")
    monkeypatch.setattr(checklist, "get_plan", fail)
    async def exercise():
        async with connected(server.create_server(ANYA)) as client:
            result = await client.call_tool("get_plan", {"intern_id": ANYA})
            assert result.isError and "Сервис временно недоступен" in text(result)
            assert "PRIVATE_CONNECTION_DETAILS" not in text(result)
            data(await client.call_tool("get_skill_profile", {"intern_id": ANYA}))
    run(exercise())
    assert "RuntimeError" in caplog.text and "PRIVATE_CONNECTION_DETAILS" not in caplog.text


@pytest.mark.parametrize("failed", [False, True])
def test_only_process_owner_closes_store_after_multiple_sessions(store, monkeypatch, failed):
    instance = server.create_server(ANYA)
    closed, loops = [], []
    close = store.close
    async def tracked_close():
        closed.append(asyncio.get_running_loop())
        await close()
    monkeypatch.setattr(store, "close", tracked_close)
    async def serve():
        for _ in range(2):
            async with connected(instance) as client:
                assert data(await client.call_tool("get_plan", {"intern_id": ANYA}))["current_day"] == 2
            assert not closed
        loops.append(asyncio.get_running_loop())
        if failed:
            raise RuntimeError("stdio failed")
    monkeypatch.setattr(instance, "run_stdio_async", serve)
    monkeypatch.setattr(server, "create_server", lambda user_id: instance)
    if failed:
        with pytest.raises(RuntimeError, match="stdio failed"):
            server.main(["--user", ANYA])
    else:
        server.main(["--user", ANYA])
    assert closed == loops


@pytest.mark.parametrize("arguments,identity", [([], None), ([], ""), ([], "unknown"), ([], "system"),
    (["--user", "unknown"], ANYA), (["--user", ""], ANYA)])
def test_invalid_startup_identity_exits_before_protocol(arguments, identity):
    environment = {**os.environ, "DATABASE_URL": "", "LLM_PROVIDER": "echo", "PYTHONUTF8": "1"}
    environment.pop("MCP_USER_ID", None)
    if identity is not None:
        environment["MCP_USER_ID"] = identity
    result = subprocess.run([sys.executable, "-m", "app.mcp_server.server", *arguments], cwd=BACKEND,
                            env=environment, input="", capture_output=True, text=True, encoding="utf-8", timeout=15)
    assert result.returncode == 2 and result.stdout == ""
    assert ("Укажите пользователя" if identity in (None, "") or arguments == ["--user", ""] else "Неизвестный пользователь") in result.stderr


@pytest.mark.parametrize("arguments,identity", [(["--user", ANYA], "unknown"), ([], ANYA)])
def test_stdio_module_entrypoint_binds_identity_once(tmp_path, arguments, identity):
    async def exercise():
        params = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server.server", *arguments],
            cwd=str(BACKEND), env={"DATABASE_URL": "", "LLM_PROVIDER": "echo", "PYTHONUTF8": "1", "MCP_USER_ID": identity})
        with (tmp_path / "stderr.log").open("w", encoding="utf-8") as stderr:
            async with stdio_client(params, errlog=stderr) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timedelta(seconds=10)) as client:
                    assert (await client.initialize()).serverInfo.name == "AI-buddy onboarding"
                    tools = (await client.list_tools()).tools
                    assert {tool.name for tool in tools if not tool.name.startswith(("mentor_", "absence_", "self_check_"))} == NAMES
                    assert all("user_id" not in t.inputSchema.get("properties", {}) for t in tools)
                    assert data(await client.call_tool("get_plan", {"intern_id": ANYA}))["current_day"] == 2
                    request = data(await client.call_tool("create_request", {"resource_id": "bitbucket-platform", "level": "read", "justification": "Демо"}))
                    assert (await client.call_tool("decide_request", {"request_id": request["id"], "approve": True, "user_id": "mentor-petr"})).isError
                    denied = await client.call_tool("get_plan", {"intern_id": "intern-ivan"})
                    absent = await client.call_tool("get_plan", {"intern_id": "missing"})
                    assert denied.isError and denied == absent
    run(exercise())
