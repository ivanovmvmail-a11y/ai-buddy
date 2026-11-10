"""SQL и транзакции адаптера: поддельный psycopg, без сервера и сети."""
import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from app import async_runner
from app.rag.embeddings import DeterministicEmbedder
from app.rag.postgres import PostgresDocumentStore
from app.rag.storage import Chunk, Document, SearchHit

run = async_runner.run


class FakeCursor:
    def __init__(self, connection, rows=None):
        self.connection = connection
        self.rows = rows or []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def fetchone(self):
        return {"id": 42}

    async def fetchall(self):
        return self.rows

    async def executemany(self, sql, params):
        self.connection.calls.append((sql, params))
        if self.connection.fail_insert:
            raise RuntimeError("chunk insert failed")


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.rows = []
        self.fail_insert = False
        self.committed = self.rolled_back = False
        self.returned = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, *args):
        self.committed = exc_type is None
        self.rolled_back = exc_type is not None
        self.returned += 1

    async def execute(self, sql, params=None):
        self.calls.append((sql, params))
        return FakeCursor(self, self.rows)

    def cursor(self):
        return FakeCursor(self)


@pytest.fixture
def database(monkeypatch):
    connection = FakeConnection()
    pool = Mock()
    pool.open = AsyncMock()
    pool.close = AsyncMock()
    pool.connection.return_value = connection
    factory = Mock(return_value=pool)
    monkeypatch.setattr("app.rag.postgres.AsyncConnectionPool", factory)
    return PostgresDocumentStore("postgresql://example.invalid/demo"), connection, factory


def vector():
    return run(DeterministicEmbedder().embed(["sample"]))[0]


def test_upsert_replaces_chunks_in_one_transaction(database):
    store, connection, factory = database
    document = Document("stable", "Title", "Body", "Авито Доставка", "https://example.invalid/doc")
    embedding = vector()
    run(store.upsert(document, [Chunk("first", embedding), Chunk("second", embedding)]))
    assert connection.committed and connection.returned == 1 and not connection.rolled_back
    factory.assert_called_once()
    assert factory.call_args.args == (store.database_url,)
    assert factory.call_args.kwargs["kwargs"]["connect_timeout"] == 5
    assert factory.call_args.kwargs["open"] is False
    assert connection.calls[0] == ("SET LOCAL search_path = public, extensions", None)
    sql, params = connection.calls[1]
    assert "ON CONFLICT (source_id) DO UPDATE" in sql
    assert params == (document.source_id, document.title, document.url, document.content, document.team)
    assert connection.calls[2] == ("DELETE FROM public.rag_chunks WHERE document_id = %s", (42,))
    sql, rows = connection.calls[3]
    assert "%s::vector" in sql
    assert [(row[0], row[1], row[2]) for row in rows] == [(42, 0, "first"), (42, 1, "second")]
    assert all(row[3].startswith("[") and len(row[3][1:-1].split(",")) == 1024 for row in rows)


def test_chunk_write_failure_rolls_back_and_returns_connection(database):
    store, connection, _ = database
    connection.fail_insert = True
    with pytest.raises(RuntimeError, match="chunk insert failed"):
        run(store.upsert(Document("source", "title", "body"), [Chunk("body", vector())]))
    assert connection.rolled_back and connection.returned == 1 and not connection.committed


def test_search_filters_before_limit_and_binds_team(database):
    store, connection, _ = database
    connection.rows = [{"title": "Guide", "content": "body", "url": None, "team": None}]
    team = "Авито Доставка' OR 1=1 --"
    assert run(store.search(vector(), team, 4)) == [SearchHit("Guide", "body", None, None)]
    assert connection.calls[1] == ("SELECT set_config('app.rag_team', %s, true)", (team,))
    sql, params = connection.calls[2]
    assert "WHERE d.team IS NULL OR d.team = %s" in sql
    assert sql.index("WHERE") < sql.index("ORDER BY") < sql.index("LIMIT")
    assert "<=> %s::vector" in sql
    assert team not in sql
    assert params[0] == team and params[2] == 4
    assert connection.committed and connection.returned == 1


def test_no_pool_for_invalid_vectors(database):
    store, connection, factory = database
    with pytest.raises(ValueError):
        run(store.search([float("inf")] * 1024, "team", 4))
    with pytest.raises(ValueError):
        run(store.upsert(Document("id", "title", "body"), [Chunk("body", [1.0])]))
    factory.assert_not_called()


def test_pool_is_lazy_reused_and_opened_on_shared_loop(database):
    store, connection, factory = database
    factory.assert_not_called()
    loops = []

    async def opened():
        loops.append(asyncio.get_running_loop())

    factory.return_value.open.side_effect = opened

    async def requests():
        await asyncio.gather(*(store.search(vector_data, "team", 4) for _ in range(3)))
        await store.upsert(Document("id", "title", "body"), [Chunk("body", vector_data)])
        return asyncio.get_running_loop()

    vector_data = vector()
    loop = run(requests())
    factory.assert_called_once()
    assert loops == [loop] * 4
    assert connection.returned == 4
    run(store.close())
    factory.return_value.close.assert_awaited_once()
    assert store._pool is None


def test_close_unused_store_does_not_create_pool(database):
    store, _, factory = database
    run(store.close())
    factory.assert_not_called()


def test_database_url_is_required():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        PostgresDocumentStore("")
