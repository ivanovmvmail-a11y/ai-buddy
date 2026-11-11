"""RAG и онбординг на одном настоящем пуле, временная БД без ключей."""
import asyncio
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, storage
from app.mcp_server.postgres import PostgresStore
from app.mcp_server.seed import load_seed
from app.rag.embeddings import DeterministicEmbedder
from app.rag.ingest import ingest_directory
from app.rag.postgres import PostgresDocumentStore
from app.rag.service import RAGService
from .conftest import apply_onboarding_migrations, MIGRATION

run = async_runner.run
RAG_MIGRATION = MIGRATION.with_name('20261110120000_rag_documents.sql')


@pytest.fixture
def shared_database(onboarding_dsn):
    params = conninfo_to_dict(onboarding_dsn)
    name = 'shared_pool_' + uuid4().hex
    with psycopg.connect(**{**params, 'dbname': 'postgres'}, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            with psycopg.connect(**{**params, 'dbname': name}, autocommit=True) as owner:
                owner.execute(RAG_MIGRATION.read_text(encoding='utf-8'))
            yield make_conninfo(**{**params, 'dbname': name})
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


@pytest.mark.parametrize('first_closed', ['rag', 'onboarding'])
def test_real_shared_pool_budget_transaction_isolation_and_owner_lifetime(shared_database, monkeypatch, first_closed):
    dsn = shared_database
    with psycopg.connect(dsn, autocommit=True) as owner:
        apply_onboarding_migrations(owner)
    rag, onboarding = PostgresDocumentStore(dsn), PostgresStore(dsn)
    service = RAGService(DeterministicEmbedder(), rag)
    monkeypatch.setattr(storage, 'get_store', lambda: onboarding)
    async def exercise():
        try:
            await ingest_directory(service)
            await onboarding.initialize(load_seed())
            pool = await rag._get_pool()
            assert await onboarding._get_pool() is pool and pool.max_size == 8
            hits = await service.retrieve('Платформа объявлений', DEMO_USERS['intern-ivan'], 100)
            assert all(hit['title'].find('Платформа объявлений') < 0 for hit in hits)
            assert (await checklist.get_plan(DEMO_USERS['intern-anya'], 'intern-anya')).current_day == 2
            async with pool.connection() as connection:
                state = await connection.execute("SELECT current_setting('app.rag_team',true) AS team, current_setting('search_path') AS path, current_setting('transaction_isolation') AS isolation")
                row = await state.fetchone()
                assert row['team'] in (None, '') and 'extensions' not in row['path']
                assert row['isolation'] == 'read committed'
            async def query():
                async with pool.connection() as connection:
                    await connection.execute('SELECT pg_sleep(0.03)')
            await asyncio.gather(*(query() for _ in range(20)))
            assert pool.get_stats()['pool_size'] <= 8
            if first_closed == 'onboarding':
                await onboarding.close()
                assert not pool.closed
                assert await service.retrieve('git', DEMO_USERS['intern-anya'])
                await rag.close()
            else:
                await rag.close()
                assert not pool.closed
                assert (await checklist.get_plan(DEMO_USERS['intern-anya'], 'intern-anya')).current_day == 2
                await onboarding.close()
            assert pool.closed
            assert await rag._get_pool() is not pool
        finally:
            await onboarding.close()
            await rag.close()
    run(exercise())


def test_missing_onboarding_schema_fallback_does_not_close_live_rag_pool(shared_database, monkeypatch):
    rag, onboarding = PostgresDocumentStore(shared_database), PostgresStore(shared_database)
    service = RAGService(DeterministicEmbedder(), rag)
    demo = storage.DemoStore(onboarding)
    monkeypatch.setattr(storage, 'get_store', lambda: demo)
    async def exercise():
        try:
            await ingest_directory(service)
            pool = await rag._get_pool()
            plan = await checklist.get_plan(DEMO_USERS['intern-anya'], 'intern-anya')
            assert plan.current_day == 2 and isinstance(demo._store, storage.InMemoryStore)
            assert onboarding._pool is None and not pool.closed
            assert await service.retrieve('git', DEMO_USERS['intern-anya'])
            await demo.close()
            assert not pool.closed
        finally:
            await onboarding.close()
            await rag.close()
    run(exercise())
