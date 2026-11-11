"""Один ленивый psycopg-пул на точный DSN и event loop, с владением адаптеров.

Вызывать через app.async_runner. Закрытие одного адаптера освобождает его долю;
физический пул закрывается только после последнего владельца.
"""
import asyncio
from dataclasses import dataclass

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


@dataclass
class _Entry:
    pool: AsyncConnectionPool
    loop: asyncio.AbstractEventLoop
    owners: int = 0


_pools: dict[str, _Entry] = {}
_lock = asyncio.Lock()


async def _acquire(database_url: str) -> AsyncConnectionPool:
    async with _lock:
        entry = _pools.get(database_url)
        if entry is None:
            pool = AsyncConnectionPool(database_url, open=False, min_size=1, max_size=8, timeout=5,
                                       kwargs={"connect_timeout": 5, "row_factory": dict_row})
            try:
                await pool.open()
            except BaseException:
                await pool.close()
                raise
            entry = _Entry(pool, asyncio.get_running_loop())
            _pools[database_url] = entry
        elif entry.loop is not asyncio.get_running_loop():
            raise RuntimeError("PostgreSQL pool belongs to another event loop; use app.async_runner")
        entry.owners += 1
        return entry.pool


async def _release(database_url: str, pool: AsyncConnectionPool) -> None:
    async with _lock:
        entry = _pools[database_url]
        if entry.pool is not pool:
            raise RuntimeError("PostgreSQL pool owner mismatch")
        entry.owners -= 1
        if entry.owners == 0:
            # Не открываем замену, пока старый пул ещё закрывается.
            try:
                await pool.close()
            finally:
                del _pools[database_url]


class PostgresPoolOwner:
    """Общая часть адаптеров; конструктор не подключается и не создаёт loop/pool."""
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL is required")
        self.database_url = database_url
        self._pool: AsyncConnectionPool | None = None
        self._pool_lock = asyncio.Lock()

    async def _get_pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            async with self._pool_lock:
                if self._pool is None:
                    self._pool = await _acquire(self.database_url)
        return self._pool

    async def close(self) -> None:
        async with self._pool_lock:
            if self._pool is not None:
                try:
                    await _release(self.database_url, self._pool)
                finally:
                    self._pool = None
