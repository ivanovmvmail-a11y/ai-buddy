"""Ревью #21: старый том, пустая база, порядок и запрет записи истории."""
import asyncio
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from app import async_runner, main
from app.agent.users import DEMO_USERS
from app.config import settings
from app.mcp_server import checklist, clock, storage
from app.mcp_server.models import AccessRequest, Reminder
from app.mcp_server.postgres import PostgresStore, TABLES
from app.mcp_server.seed import load_seed
from app.mcp_server.seed.__main__ import main as seed_main
from .conftest import apply_onboarding_migrations, MIGRATION, docker_command

run = async_runner.run
ANYA = DEMO_USERS['intern-anya']
BACKEND = Path(__file__).resolve().parents[2]


@pytest.mark.skipif(os.name == 'nt', reason='Проверяется Linux CMD контейнера через /bin/sh')
@pytest.mark.parametrize('seed_exit,rag_exit', [(1, 0), (1, 1), (0, 0)])
def test_docker_command_starts_server_after_seed_failure(tmp_path, seed_exit, rag_exit):
    command = next(line for line in (BACKEND / 'Dockerfile').read_text(encoding='utf-8').splitlines() if line.startswith('CMD '))
    (tmp_path / 'python').write_text('#!/bin/sh\ncase "$*" in *mcp_server.seed*) exit "$SEED_EXIT";; *) exit "$RAG_EXIT";; esac\n')
    (tmp_path / 'gunicorn').write_text('#!/bin/sh\nprintf "%s" "$*" > "$SERVER_MARKER"\n')
    for name in ('python', 'gunicorn'):
        (tmp_path / name).chmod(0o755)
    marker = tmp_path / 'server-started'
    result = subprocess.run(json.loads(command[4:]), env={**os.environ,
        'PATH': str(tmp_path) + os.pathsep + os.environ['PATH'], 'SERVER_MARKER': str(marker),
        'SEED_EXIT': str(seed_exit), 'RAG_EXIT': str(rag_exit)}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'app.main:app' in marker.read_text()
    if seed_exit:
        assert 'onboarding seed failed' in result.stdout


@pytest.mark.parametrize('error', [psycopg.errors.UndefinedTable('private connection details'),
                                   psycopg.OperationalError('private connection details'),
                                   RuntimeError('private connection details')])
def test_lazy_bootstrap_failure_keeps_one_seeded_memory_store(error, caplog):
    class FailingPrimary(storage.InMemoryStore):
        calls = 0
        closed = 0
        async def initialize(self, data, *, reset=False):
            self.calls += 1
            await asyncio.sleep(0)
            raise error
        async def close(self):
            self.closed += 1
    primary = FailingPrimary()
    store = storage.DemoStore(primary)
    async def first_reads():
        async def read():
            async with store.read() as data:
                return data.interns[ANYA.id].current_day
        assert await asyncio.gather(*(read() for _ in range(10))) == [2] * 10
        async with store.transaction(include_events=False, copy_on_commit=False) as data:
            data.items['anya.w1.notes'].status = 'done'
        async with store.read() as data:
            assert data.items['anya.w1.notes'].status == 'done'
    run(first_reads())
    assert primary.calls == primary.closed == 1
    assert isinstance(store._store, storage.InMemoryStore)
    assert len([r for r in caplog.records if r.name == "ai_buddy.onboarding"]) == 1
    assert 'InMemoryStore' in caplog.text and 'private connection details' not in caplog.text
    if isinstance(error, psycopg.errors.UndefinedTable):
        assert 'Таблицы онбординга не найдены' in caplog.text
        assert 'миграцию' in caplog.text and 'docker compose down -v' in caplog.text


def test_cli_reset_does_not_report_success_for_memory_when_database_seed_fails(monkeypatch, caplog, capsys):
    primary = storage.InMemoryStore()
    async def fail(*args, **kwargs):
        raise psycopg.errors.UndefinedTable()
    monkeypatch.setattr(primary, 'initialize', fail)
    store = storage.DemoStore(primary)
    monkeypatch.setattr(storage, 'get_store', lambda: store)
    with pytest.raises(SystemExit) as error:
        seed_main(['--reset'])
    assert error.value.code == 1
    assert not store._ready and store._store is primary
    assert 'seed reset' not in capsys.readouterr().out
    assert 'Таблицы онбординга не найдены' in caplog.text


def test_failed_service_write_is_not_retried_or_redirected_to_fallback():
    primary = storage.InMemoryStore()
    store = storage.DemoStore(primary)
    async def exercise():
        with pytest.raises(RuntimeError, match='service failed'):
            async with store.transaction() as data:  # Первая операция — запись, а не чтение.
                data.items['anya.w1.notes'].status = 'done'
                raise RuntimeError('service failed')
        async with store.read() as data:
            assert data.items['anya.w1.notes'].status == 'not_started'
        assert store._store is primary
    run(exercise())


def test_store_preserves_insertion_order_on_reads_and_updates(store):
    seed = load_seed()
    for name, *_ in TABLES:
        records = getattr(seed, name)
        setattr(seed, name, dict(reversed(list(records.items()))))
    template = seed.items['anya.w1.notes']
    for key in ('X-2', 'X-10'):
        seed.items[key] = template.model_copy(update={'id': key})
    for key, resource in (('REQ-10', 'jira'), ('REQ-2', 'confluence')):
        seed.requests[key] = AccessRequest(id=key, intern_id=ANYA.id, resource_id=resource, level='read',
            justification='Демо-запрос', status='granted', created_day=2,
            created_at=template.updated_at, updated_at=template.updated_at)
    for key, item in zip(('REM-z', 'REM-a', 'REM-m'), list(seed.items)[:3]):
        seed.reminders[key] = Reminder(id=key, user_id=ANYA.id, plan_item_id=item,
                                      text='Демо-напоминание', status='active', created_day=2)
    run(store.initialize(seed, reset=True))
    async def compare_and_update():
        async with store.read() as data:
            for name, *_ in TABLES:
                assert list(getattr(data, name)) == list(getattr(seed, name)), name
        async with store.transaction(include_events=False, copy_on_commit=False) as data:
            data.resources[next(iter(data.resources))].title += ' (обновлено)'
        async with store.read() as data:
            assert list(data.resources) == list(seed.resources)
    run(compare_and_update())
    assert [reminder.id for reminder in run(clock.list_reminders(ANYA))] == ['REM-z', 'REM-a', 'REM-m']


def test_historical_read_rejects_appended_events_and_rolls_back(store, snapshot):
    before = snapshot()
    async def append():
        async with store.read(include_events=True) as data:
            data.events = [*data.events, load_seed().events[0]]
    with pytest.raises(RuntimeError, match='Historical reads must not append events'):
        run(append())
    assert snapshot() == before


def test_historical_guard_also_runs_with_python_optimization(store):
    environment = {**os.environ, 'DATABASE_URL': '', 'LLM_PROVIDER': 'echo',
                   'TEST_ONBOARDING_DSN': store.database_url if isinstance(store, PostgresStore) else ''}
    result = subprocess.run([sys.executable, '-O', '-c', '''
import os
from app.async_runner import run
from app.mcp_server.storage import InMemoryStore
from app.mcp_server.postgres import PostgresStore
from app.mcp_server.seed import load_seed
s = PostgresStore(os.environ['TEST_ONBOARDING_DSN']) if os.environ['TEST_ONBOARDING_DSN'] else InMemoryStore(load_seed())
async def check():
    try:
        async with s.read(include_events=True) as data:
            data.events = [*data.events, load_seed().events[0]]
    except RuntimeError as error:
        print(str(error))
    else:
        raise RuntimeError('Historical read guard was disabled')
    finally:
        await s.close()
run(check())
'''], env=environment, cwd=BACKEND, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'Historical reads must not append events' in result.stdout


def test_docker_helper_respects_endpoint_and_context(monkeypatch):
    monkeypatch.setenv('DOCKER_HOST', 'npipe:////./pipe/docker_engine')
    monkeypatch.setenv('DOCKER_CONTEXT', 'desktop-linux')
    def fake_run(command, **kwargs):
        assert command == ['docker', 'version']
        assert 'env' not in kwargs
        assert os.environ['DOCKER_HOST'] == 'npipe:////./pipe/docker_engine'
        assert os.environ['DOCKER_CONTEXT'] == 'desktop-linux'
        return subprocess.CompletedProcess(command, 0, stdout='ok\n')
    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert docker_command('version') == 'ok'


@contextmanager
def isolated_database(dsn):
    params = conninfo_to_dict(dsn)
    name = f'onboarding_review_{uuid4().hex}'
    with psycopg.connect(**{**params, 'dbname': 'postgres'}, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            yield make_conninfo(**{**params, 'dbname': name})
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.mark.parametrize('has_schema', [False, True], ids=['existing-rag-volume', 'empty-onboarding-tables'])
def test_first_http_request_bootstraps_empty_tables_or_falls_back_for_existing_volume(onboarding_dsn, monkeypatch, caplog, has_schema):
    with isolated_database(onboarding_dsn) as dsn:
        with psycopg.connect(dsn, autocommit=True) as connection:
            connection.execute((MIGRATION.parent / '20261110120000_rag_documents.sql').read_text(encoding='utf-8'))
            if has_schema:
                apply_onboarding_migrations(connection)
                assert connection.execute('SELECT count(*) FROM intern_state').fetchone() == (0,)
        monkeypatch.setattr(settings, 'database_url', dsn)
        storage.get_store.cache_clear()
        store = storage.get_store()
        try:
            if not has_schema:
                with pytest.raises(SystemExit):
                    seed_main([])  # Неудачный preflight Docker со старым томом.
                caplog.clear()
            client = main.create_app().test_client()  # Настоящая фабрика, без fresh_onboarding.
            assert client.get('/health').status_code == 200
            headers = {'X-User-Id': ANYA.id}
            response = client.get('/plan', headers=headers)
            assert response.status_code == 200, response.json
            assert response.json['current_day'] == 2 and response.json['items']
            assert client.post('/plan/items/anya.w1.notes/status', headers=headers,
                               json={'status': 'done'}).status_code == 200
            response = client.get('/plan', headers=headers)
            assert next(item for item in response.json['items'] if item['id'] == 'anya.w1.notes')['status'] == 'done'
            assert client.get('/plan?intern_id=intern-ivan', headers=headers).status_code == 404
            if has_schema:
                with psycopg.connect(dsn) as connection:
                    assert connection.execute('SELECT count(*) FROM intern_state').fetchone() == (len(load_seed().interns),)
                    assert connection.execute("SELECT status FROM plan_items WHERE id='anya.w1.notes'").fetchone() == ('done',)
                assert isinstance(store._store, PostgresStore)
                run(store.close())
                storage.get_store.cache_clear()
                store = storage.get_store()
                assert next(item for item in run(checklist.get_plan(ANYA, ANYA.id)).items if item.id == 'anya.w1.notes').status == 'done'
            else:
                assert isinstance(store._store, storage.InMemoryStore)
                assert 'Таблицы онбординга не найдены' in caplog.text and 'docker compose down -v' in caplog.text
                assert len([record for record in caplog.records if 'InMemoryStore' in record.message]) == 1
                with psycopg.connect(dsn) as connection:
                    assert connection.execute("SELECT to_regclass('public.intern_state')").fetchone() == (None,)
        finally:
            run(store.close())
            storage.get_store.cache_clear()
