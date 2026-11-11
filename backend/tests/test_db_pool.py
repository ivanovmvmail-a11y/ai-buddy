"""Пул общий по DSN, владение адаптеров и гонки первого открытия/закрытия."""
import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app import async_runner
from app.db import pool as pools
from app.mcp_server.postgres import PostgresStore
from app.rag.postgres import PostgresDocumentStore

run = async_runner.run


def fake_pool():
    return Mock(open=AsyncMock(), close=AsyncMock())


def test_two_adapters_and_concurrent_first_requests_share_one_pool(monkeypatch):
    factory = Mock(side_effect=lambda *a, **k: fake_pool())
    monkeypatch.setattr(pools, 'AsyncConnectionPool', factory)
    dsn = 'postgresql://example.invalid/' + uuid4().hex
    rag, onboarding = PostgresDocumentStore(dsn), PostgresStore(dsn)
    assert rag._pool is None and onboarding._pool is None
    factory.assert_not_called()
    async def exercise():
        try:
            results = await asyncio.gather(*(owner._get_pool() for owner in [rag, onboarding] * 10))
            assert all(pool is results[0] for pool in results)
            factory.assert_called_once()
            results[0].open.assert_awaited_once()
            assert factory.call_args.kwargs['max_size'] == 8
            await rag.close()
            await rag.close()
            results[0].close.assert_not_awaited()
            assert await onboarding._get_pool() is results[0]
            await onboarding.close()
            results[0].close.assert_awaited_once()
        finally:
            await rag.close()
            await onboarding.close()
    run(exercise())


def test_different_dsns_never_share_connections(monkeypatch):
    factory = Mock(side_effect=lambda *a, **k: fake_pool())
    monkeypatch.setattr(pools, 'AsyncConnectionPool', factory)
    first = PostgresDocumentStore('postgresql://reader@example.invalid/' + uuid4().hex)
    second = PostgresStore('postgresql://owner@example.invalid/' + uuid4().hex)
    async def exercise():
        try:
            a, b = await asyncio.gather(first._get_pool(), second._get_pool())
            assert a is not b and factory.call_count == 2
            await first.close()
            a.close.assert_awaited_once()
            b.close.assert_not_awaited()
        finally:
            await first.close()
            await second.close()
    run(exercise())


@pytest.mark.parametrize('error_type', [RuntimeError, asyncio.CancelledError])
def test_failed_or_cancelled_open_is_closed_and_can_retry(monkeypatch, error_type):
    failed, healthy = fake_pool(), fake_pool()
    failed.open.side_effect = error_type('open failed')
    factory = Mock(side_effect=[failed, healthy])
    monkeypatch.setattr(pools, 'AsyncConnectionPool', factory)
    owner = PostgresStore('postgresql://example.invalid/' + uuid4().hex)
    async def exercise():
        try:
            with pytest.raises(error_type):
                await owner._get_pool()
            assert owner._pool is None
            failed.close.assert_awaited_once()
            assert await owner._get_pool() is healthy
        finally:
            await owner.close()
    run(exercise())
    healthy.close.assert_awaited_once()


def test_replacement_waits_until_previous_pool_is_closed(monkeypatch):
    first, second = fake_pool(), fake_pool()
    factory = Mock(side_effect=[first, second])
    monkeypatch.setattr(pools, 'AsyncConnectionPool', factory)
    dsn = 'postgresql://example.invalid/' + uuid4().hex
    a, b = PostgresStore(dsn), PostgresDocumentStore(dsn)
    async def exercise():
        closing, finish_close = asyncio.Event(), asyncio.Event()
        async def slow_close():
            closing.set()
            await finish_close.wait()
        first.close.side_effect = slow_close
        try:
            assert await a._get_pool() is first
            closed = asyncio.create_task(a.close())
            await closing.wait()
            opened = asyncio.create_task(b._get_pool())
            await asyncio.sleep(0)
            assert factory.call_count == 1
            finish_close.set()
            await closed
            assert await opened is second and factory.call_count == 2
        finally:
            finish_close.set()
            await a.close()
            await b.close()
    run(exercise())
