"""T3: один контракт, долговечность, приватность миграции и стоимость чтений."""
import asyncio
from datetime import timedelta, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock, events, hiring
from app.mcp_server._domain import timestamp
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import Conflict
from app.mcp_server.models import Event, OnboardingData
from app.mcp_server.postgres import PostgresStore, TABLES
from app.mcp_server.seed import load_seed
from .conftest import apply_onboarding_migrations, MIGRATION

run = async_runner.run
ANYA = DEMO_USERS["intern-anya"]
BACKEND = Path(__file__).resolve().parents[2]


def test_read_views_and_fast_writes_do_not_copy_large_event_history(store, edit, monkeypatch):
    baseline = len(load_seed().events) + 10000
    entry = Event(ts=load_seed().items["anya.w1.notes"].updated_at, user_id=ANYA.id, role=ANYA.role,
                  team=ANYA.team, type="history", payload={"intern_id": ANYA.id, "day": 1})
    edit(lambda data: data.events.extend(entry.model_copy(deep=True) for _ in range(10000)))
    def forbidden_copy(*args, **kwargs):
        pytest.fail("A service read/write must not deepcopy old events")
    monkeypatch.setattr(Event, "__deepcopy__", forbidden_copy)
    async def event_count():
        if not isinstance(store, PostgresStore):
            return len(store._data.events)
        async with (await store._get_pool()).connection() as connection:
            cursor = await connection.execute("SELECT count(*) AS count FROM public.events")
            return (await cursor.fetchone())["count"]
    include_events = []
    if isinstance(store, PostgresStore):
        original = store._load
        async def loaded(connection, **kwargs):
            include_events.append(kwargs["include_events"])
            return await original(connection, **kwargs)
        monkeypatch.setattr(store, "_load", loaded)
    plan = run(checklist.get_plan(ANYA, ANYA.id))
    assert plan.current_day == 2
    run(hiring.get_skill_profile(ANYA, ANYA.id))
    run(access.list_resources(ANYA))
    assert run(event_count()) == baseline + 2  # Только plan_viewed/next_step_shown, без перезаписи истории.
    run(checklist.set_item_status(ANYA, "anya.w1.notes", "done"))
    assert run(event_count()) == baseline + 3
    if include_events:
        assert not any(include_events)  # PostgreSQL не SELECT-ит историю для этих операций.


def test_service_results_cannot_mutate_stored_models(store, snapshot):
    profile = run(hiring.get_skill_profile(ANYA, ANYA.id))
    profile.skills["git"] = "confident"
    profile.strengths.clear()
    resources = run(access.list_resources(ANYA))
    resources[0].fields.clear()
    request = run(access.create_request(ANYA, "jira", "read", "Учебная задача"))
    request.justification = "подмена"
    listed = run(access.list_requests(ANYA))
    listed[0].status = "rejected"
    fact = run(checklist.weekly_summary(ANYA, ANYA.id, 1))["closed"][0]
    fact["title"] = "подмена"
    history = run(events.list_events(SYSTEM_ACTOR))
    history[0].payload.clear()
    data = snapshot()
    assert data.profiles[ANYA.id].skills["git"] == "novice" and data.profiles[ANYA.id].strengths
    assert all(resource.fields for resource in data.resources.values())
    assert data.requests[request.id].justification == "Учебная задача"
    assert data.requests[request.id].status == "granted" and data.events[0].payload


def test_read_audit_events_roll_back_on_failure(store, snapshot):
    before = snapshot()
    async def fail():
        with pytest.raises(RuntimeError):
            async with store.read() as data:
                events._record(data, ANYA, "plan_viewed", {"intern_id": ANYA.id})
                raise RuntimeError("abort telemetry")
    run(fail())
    assert snapshot() == before


def test_read_models_are_detached_from_persisted_state(store, snapshot):
    before = snapshot()
    async def modify_local_results():
        async with store.read(include_events=True) as data:
            data.profiles[ANYA.id].skills["git"] = "confident"
            data.items["anya.w1.notes"].status = "done"
            data.events[0].payload.clear()
            assert len(data.events[:1]) == 1
    run(modify_local_results())
    assert snapshot() == before


def test_initialize_preserves_partial_nonempty_store_unless_reset(store):
    entry = load_seed().events[0].model_copy(update={"type": "preexisting", "payload": {}})
    run(store.initialize(OnboardingData(events=[entry]), reset=True))
    run(store.initialize(load_seed()))
    async def inspect():
        async with store.transaction() as data:
            assert not data.interns
            assert [event.type for event in data.events] == ["preexisting"]
    run(inspect())


def test_waiting_days_use_utc_virtual_date_after_timestamp_roundtrip(store, edit):
    def change_offset(data):
        item = data.items["ivan.w1.team-space"]
        item.updated_at = item.updated_at.astimezone(timezone(timedelta(hours=14)))
    edit(change_offset)
    plan = run(checklist.get_plan(DEMO_USERS["intern-ivan"], "intern-ivan"))
    assert next(item for item in plan.items if item.id == "ivan.w1.team-space").waiting_days == 3


def child(dsn, code=None, *arguments):
    environment = {**os.environ, "DATABASE_URL": dsn, "LLM_PROVIDER": "echo"}
    command = [sys.executable, "-c", code] if code is not None else [sys.executable, "-m", "app.mcp_server.seed", *arguments]
    result = subprocess.run(command, cwd=BACKEND, env=environment, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_ac5_state_survives_process_restart_and_cli_reset_targets_database(onboarding_dsn):
    dsn = onboarding_dsn
    assert "PostgresStore" in child(dsn, None, "--reset")
    child(dsn, """
from app.async_runner import run
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock, hiring, storage
a = DEMO_USERS['intern-anya']
run(checklist.set_item_status(a, 'anya.w1.notes', 'done'))
run(access.create_request(a, 'bitbucket-platform', 'read', 'Учебная задача'))
run(hiring.set_skill_level(DEMO_USERS['mentor-petr'], a.id, 'git', 'familiar'))
run(clock.advance_day(a, a.id))
run(clock.advance_day(a, a.id))
run(storage.get_store().close())
""")
    assert "existing data preserved" in child(dsn)  # Повторный запуск Docker/CLI не стирает прогресс.
    inspect_code = """
import json
from app.async_runner import run
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock, hiring, storage
a = DEMO_USERS['intern-anya']
p = run(checklist.get_plan(a, a.id))
print(json.dumps({'day': p.current_day, 'notes': next(i.status for i in p.items if i.id == 'anya.w1.notes'),
 'git': run(hiring.get_skill_profile(a, a.id)).skills['git'],
 'requests': len(run(access.list_requests(a))), 'reminders': sorted(r.kind for r in run(clock.list_reminders(a)))}))
run(storage.get_store().close())
"""
    persisted = json.loads(child(dsn, inspect_code))
    # Два прежних напоминания и уведомление о смене навыка сохраняются после перезапуска.
    assert persisted == {"day": 4, "notes": "done", "git": "familiar", "requests": 1, "reminders": ["access_request", "plan_item", "skill_changed"]}
    child(dsn, None, "--reset")
    restored = json.loads(child(dsn, inspect_code))
    assert restored == {"day": 2, "notes": "not_started", "git": "novice", "requests": 0, "reminders": []}


def test_two_pools_serialize_seed_and_duplicate_requests(onboarding_dsn):
    first, second = PostgresStore(onboarding_dsn), PostgresStore(onboarding_dsn)
    async def exercise():
        try:
            await first.initialize(OnboardingData(), reset=True)
            await asyncio.gather(first.initialize(load_seed()), second.initialize(load_seed()))
            async with first.read(include_events=True) as data:
                assert len(data.events) == len(load_seed().events)
            # Две транзакции от разных соединений/пулов проверяют один и тот же ресурс.
            async def submit(store):
                async with store.transaction(include_events=False, copy_on_commit=False) as data:
                    if any(r.intern_id == ANYA.id for r in data.requests.values()):
                        raise Conflict()
                    from app.mcp_server.models import AccessRequest
                    request = AccessRequest(id="REQ-1004", intern_id=ANYA.id, resource_id="jira", level="read",
                        justification="Учебная задача", status="granted", created_day=2,
                        created_at=timestamp(data, ANYA.id), updated_at=timestamp(data, ANYA.id))
                    data.requests[request.id] = request
            results = await asyncio.gather(submit(first), submit(second), return_exceptions=True)
            assert sum(isinstance(result, Conflict) for result in results) == 1
            assert sum(result is None for result in results) == 1
        finally:
            await first.close()
            await second.close()
    run(exercise())


def test_sql_failure_rolls_back_saved_plan_request_and_events(onboarding_dsn, monkeypatch):
    from app.mcp_server import storage
    store = PostgresStore(onboarding_dsn)
    run(store.initialize(load_seed(), reset=True))
    monkeypatch.setattr(storage, "get_store", lambda: store)
    with psycopg.connect(onboarding_dsn) as connection:
        connection.execute("""CREATE FUNCTION onboarding_test_fail_event() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN IF NEW.type = 'access_request_created' AND NEW.user_id = 'intern-anya' THEN
            RAISE EXCEPTION 'simulated event storage failure'; END IF; RETURN NEW; END $$""")
        connection.execute("CREATE TRIGGER onboarding_test_fail BEFORE INSERT ON public.events FOR EACH ROW EXECUTE FUNCTION onboarding_test_fail_event()")
    try:
        with pytest.raises(psycopg.errors.RaiseException):
            run(access.create_request(ANYA, "jira", "read", "Учебная задача"))
        with psycopg.connect(onboarding_dsn) as connection:
            assert connection.execute("SELECT count(*) FROM access_requests WHERE intern_id='intern-anya'").fetchone() == (0,)
            assert connection.execute("SELECT status FROM plan_items WHERE id='anya.w1.access-base'").fetchone() == ("not_started",)
            assert connection.execute("SELECT count(*) FROM events").fetchone() == (len(load_seed().events),)
    finally:
        run(store.close())
        with psycopg.connect(onboarding_dsn) as connection:
            connection.execute("DROP TRIGGER onboarding_test_fail ON public.events; DROP FUNCTION onboarding_test_fail_event()")


def test_pool_is_lazy_and_created_only_on_shared_event_loop(onboarding_dsn, monkeypatch):
    from psycopg_pool import AsyncConnectionPool
    original = AsyncConnectionPool.__init__
    loops = []
    def created(self, *args, **kwargs):
        loops.append(asyncio.get_running_loop())
        original(self, *args, **kwargs)
    monkeypatch.setattr(AsyncConnectionPool, "__init__", created)
    store = PostgresStore(onboarding_dsn)
    assert not loops and store._pool is None
    async def use():
        try:
            async with store.read():
                pass
            pool = store._pool
            async with store.read():
                pass
            assert store._pool is pool
            assert loops == [asyncio.get_running_loop()]
        finally:
            await store.close()
    run(use())
    assert store._pool is None


@pytest.mark.parametrize("api_roles", [False, True])
def test_migration_on_clean_postgres_closes_default_public_grants(onboarding_dsn, api_roles):
    params = conninfo_to_dict(onboarding_dsn)
    database = f"onboarding_migration_{uuid4().hex}"
    reader = f"onboarding_reader_{uuid4().hex[:10]}"
    with psycopg.connect(**{**params, "dbname": "postgres"}, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            with psycopg.connect(**{**params, "dbname": database}, autocommit=True) as owner:
                if api_roles:
                    owner.execute("CREATE ROLE anon; CREATE ROLE authenticated")
                    owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
                    owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated")
                owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC")
                owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO PUBLIC")
                apply_onboarding_migrations(owner)
                owner.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(reader)))
                for _, table, *_ in TABLES:
                    owner.execute(sql.SQL("GRANT SELECT ON {} TO {}").format(sql.Identifier("public", table), sql.Identifier(reader)))
                    if api_roles:
                        for role in ("anon", "authenticated"):
                            assert owner.execute("SELECT has_table_privilege(%s,%s,'SELECT,INSERT,UPDATE,DELETE')", (role, f"public.{table}")).fetchone() == (False,)
                            sequence = owner.execute("SELECT pg_get_serial_sequence(%s, 'seq')", (f"public.{table}",)).fetchone()[0]
                            assert owner.execute("SELECT has_sequence_privilege(%s,%s,'USAGE,SELECT,UPDATE')", (role, sequence)).fetchone() == (False,)
                if api_roles:
                    for role in ("anon", "authenticated"):
                        assert owner.execute("SELECT has_table_privilege(%s,'public.events','SELECT,INSERT')", (role,)).fetchone() == (False,)
                        assert owner.execute("SELECT has_sequence_privilege(%s,'public.events_id_seq','USAGE,SELECT,UPDATE')", (role,)).fetchone() == (False,)
                owner.execute("INSERT INTO intern_state (intern_id, start_date, current_day) VALUES ('intern-private', '2026-11-10', 2)")
                with owner.transaction():
                    owner.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(reader)))
                    assert owner.execute("SELECT count(*) FROM intern_state").fetchone() == (0,)
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(reader)))
            if api_roles:
                admin.execute("DROP ROLE IF EXISTS anon; DROP ROLE IF EXISTS authenticated")
