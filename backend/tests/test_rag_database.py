"""Опциональные тесты миграции/пула: --rag-postgres, только временный локальный Docker.

Нужен уже скачанный pgvector/pgvector:pg17; тест сам не обращается к интернету.
"""
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.rag.embeddings import DeterministicEmbedder
from app.rag.ingest import DEMO_DOCS, ingest_directory, read_document
from app.rag.postgres import PostgresDocumentStore
from app.rag.service import RAGService

MIGRATION = Path(__file__).resolve().parents[2] / "supabase/migrations/20261110120000_rag_documents.sql"


@pytest.mark.parametrize("schema_exists", [True, False])
def test_cli_process_exits_without_pending_pool_workers(postgres_cluster, schema_exists):
    params = postgres_cluster
    database = f"rag_cli_{uuid4().hex}"
    with psycopg.connect(**params, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        try:
            if schema_exists:
                with psycopg.connect(**params, dbname=database, autocommit=True) as owner:
                    owner.execute(MIGRATION.read_text(encoding="utf-8"))
            environment = {**os.environ, "DATABASE_URL": make_conninfo(**params, dbname=database),
                           "LLM_PROVIDER": "echo", "EMBEDDINGS_PROVIDER": "fake"}
            result = subprocess.run([sys.executable, "-m", "app.rag.ingest"],
                cwd=Path(__file__).resolve().parents[1], env=environment, capture_output=True, text=True, timeout=30)
            assert result.returncode == (0 if schema_exists else 1), result.stderr
            assert ("Loaded 22 documents" in result.stdout) == schema_exists
            assert "Task was destroyed" not in result.stderr
            assert "AsyncConnectionPool.worker" not in result.stderr
        finally:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database)))


@pytest.fixture(scope="module")
def postgres_cluster(request):
    if not request.config.getoption("--rag-postgres"):
        pytest.skip("Use --rag-postgres with a cached local pgvector image")
    # Явно локальный управляемый daemon; внешние Docker contexts не используются.
    environment = {key: value for key, value in os.environ.items() if key not in {
        "DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH",
    }}
    name = f"ai-buddy-rag-tests-{uuid4().hex[:12]}"

    def docker(*args):
        return subprocess.run(
            ["docker", "--host=unix:///var/run/docker.sock", *args], env=environment,
            check=True, text=True, capture_output=True, timeout=60,
        ).stdout.strip()

    docker("run", "--detach", "--rm", "--pull=never", "--name", name,
           "-e", "POSTGRES_USER=rag_test", "-e", "POSTGRES_PASSWORD=rag-test-only",
           "-p", "127.0.0.1::5432", "pgvector/pgvector:pg17")
    try:
        port = int(docker("port", name, "5432/tcp").split(":")[-1])
        params = dict(host="127.0.0.1", port=port, user="rag_test", password="rag-test-only", connect_timeout=1)
        deadline = time.monotonic() + 30
        while True:
            try:
                with psycopg.connect(**params, dbname="postgres"):
                    break
            except psycopg.OperationalError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.1)
        yield params
    finally:
        docker("rm", "--force", name)


@pytest.mark.parametrize("api_roles,existing_vector_schema", [
    (False, None), (True, None), (False, "public"), (True, "extensions"),
])
def test_migration_privileges_and_pooled_team_isolation(postgres_cluster, api_roles, existing_vector_schema):
    params = postgres_cluster
    database_name = f"rag_test_{uuid4().hex}"
    reader = f"rag_reader_{uuid4().hex[:12]}"
    owner_store = reader_store = None
    with psycopg.connect(**params, dbname="postgres", autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
        try:
            with psycopg.connect(**params, dbname=database_name, autocommit=True) as owner:
                owner.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD 'reader-test-only'").format(sql.Identifier(reader)))
                if api_roles:
                    owner.execute("CREATE ROLE anon; CREATE ROLE authenticated")
                    owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated")
                    owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated")
                # Проверяем также закрытие доступа через PUBLIC, не только прямых grants.
                owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO PUBLIC")
                owner.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO PUBLIC")
                if existing_vector_schema:
                    owner.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(existing_vector_schema)))
                    owner.execute(sql.SQL("CREATE EXTENSION vector WITH SCHEMA {}").format(sql.Identifier(existing_vector_schema)))
                owner.execute(MIGRATION.read_text(encoding="utf-8"))
                schema = owner.execute("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON n.oid=e.extnamespace WHERE e.extname='vector'").fetchone()[0]
                assert schema == (existing_vector_schema or "extensions")
                if api_roles:
                    for role in ("anon", "authenticated"):
                        for table in ("rag_documents", "rag_chunks"):
                            assert owner.execute("SELECT has_table_privilege(%s, %s, 'SELECT,INSERT,UPDATE,DELETE')", (role, f"public.{table}")).fetchone() == (False,)
                            assert owner.execute("SELECT has_sequence_privilege(%s, %s, 'USAGE,SELECT,UPDATE')", (role, f"public.{table}_id_seq")).fetchone() == (False,)
                        with owner.transaction():
                            owner.execute(sql.SQL("SET LOCAL ROLE {}").format(sql.Identifier(role)))
                            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                                with owner.transaction():
                                    owner.execute("SELECT content, embedding FROM public.rag_chunks")
                owner.execute(sql.SQL("GRANT SELECT ON rag_documents, rag_chunks TO {}").format(sql.Identifier(reader)))
                owner.execute(sql.SQL("GRANT USAGE ON SCHEMA public, extensions TO {}").format(sql.Identifier(reader)))

            owner_store = PostgresDocumentStore(make_conninfo(**params, dbname=database_name))
            service = RAGService(DeterministicEmbedder(), owner_store)
            assert async_runner.run(ingest_directory(service)) == (22, 22)
            pool = owner_store._pool
            assert async_runner.run(ingest_directory(service)) == (22, 22)
            for user in DEMO_USERS.values():
                hits = async_runner.run(service.retrieve("Лиловый конструктор", user, 100))
                assert len(hits) == (16 if user.team in {"Авито Доставка", "Платформа объявлений"} else 10)
                assert all(not hit["title"].startswith(team) or team == user.team
                           for team in ("Авито Доставка", "Платформа объявлений") for hit in hits)
            # Новые how-to хранятся с тем же source_id и scope после повторного CLI/ingest.
            documents = [read_document(path, f"demo:{path.name}") for path in DEMO_DOCS.glob("*.md")]
            for user_id in ("intern-anya", "intern-ivan", "hrbp-elena"):
                user = DEMO_USERS[user_id]
                allowed = {doc.title for doc in documents if doc.team in (None, user.team)}
                for doc in documents:
                    if doc.team in (None, user.team):
                        continue
                    hits = async_runner.run(service.retrieve(doc.content, user, 100))
                    assert {hit["title"] for hit in hits} == allowed
                    if doc.team is not None and doc.team != user.team:
                        assert doc.title not in {hit["title"] for hit in hits}
                        top = async_runner.run(service.retrieve(doc.content, user, 1))
                        assert top and top[0]["title"] in allowed
            with psycopg.connect(**params, dbname=database_name) as owner:
                assert owner.execute("SELECT count(*) FROM public.rag_documents").fetchone() == (22,)
                assert owner.execute("SELECT count(*) FROM public.rag_chunks").fetchone() == (22,)
            assert owner_store._pool is pool
            reader_params = {**params, "user": reader, "password": "reader-test-only", "dbname": database_name}
            reader_store = PostgresDocumentStore(make_conninfo(**reader_params))
            reader_service = RAGService(DeterministicEmbedder(), reader_store)
            assert len(async_runner.run(reader_service.retrieve("Лиловый конструктор", DEMO_USERS["intern-ivan"], 100))) == 16

            async def check_returned_connection():
                async with (await reader_store._get_pool()).connection() as connection:
                    cursor = await connection.execute("SELECT count(*) AS count FROM public.rag_documents")
                    assert (await cursor.fetchone())["count"] == 8
                    cursor = await connection.execute("SELECT count(*) AS count FROM public.rag_chunks")
                    assert (await cursor.fetchone())["count"] == 8

            async_runner.run(check_returned_connection())
        finally:
            for store in (owner_store, reader_store):
                if store is not None:
                    async_runner.run(store.close())
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name)))
            admin.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(reader)))
            if api_roles:
                admin.execute("DROP ROLE IF EXISTS anon; DROP ROLE IF EXISTS authenticated")
