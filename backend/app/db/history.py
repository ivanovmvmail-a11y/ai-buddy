"""Переписка в PostgreSQL (SPEC §9; Claude 13.11 по записке HANDOFF 11.11) — протокол `app.agent.history.HistoryStore`.

Таблица — миграция `20261113130000_chat_and_actions.sql`. Адаптер для `app.agent.history.make_history_store`.
"""
from psycopg.types.json import Jsonb

from app.agent.history import HISTORY_LIMIT, ChatEntry, InMemoryHistoryStore
from app.config import settings

from ._table import _TableOrMemory


class PostgresHistoryStore(_TableOrMemory):
    table = "chat_messages"

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url, InMemoryHistoryStore())

    async def append(self, entry: ChatEntry) -> None:
        if not await self._use_db():
            return await self._fallback.append(entry)
        async with (await self._get_pool()).connection() as connection:
            await connection.execute(
                "INSERT INTO public.chat_messages (id, user_id, role, content, sources, answer_id, scripted, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (entry.id, entry.user_id, entry.role, entry.content, Jsonb(entry.sources), entry.answer_id,
                 entry.scripted, entry.created_at))

    async def list(self, user_id: str, limit: int = HISTORY_LIMIT) -> list[ChatEntry]:
        if limit <= 0:
            return []
        if not await self._use_db():
            return await self._fallback.list(user_id, limit)
        async with (await self._get_pool()).connection() as connection:
            rows = await (await connection.execute(
                "SELECT id, user_id, role, content, sources, answer_id, scripted, created_at FROM ("
                " SELECT * FROM public.chat_messages WHERE user_id = %s ORDER BY seq DESC LIMIT %s"
                ") last ORDER BY seq", (user_id, limit))).fetchall()
        return [ChatEntry.model_validate(row) for row in rows]

    async def clear(self) -> None:
        if not await self._use_db():
            return await self._fallback.clear()
        async with (await self._get_pool()).connection() as connection:
            await connection.execute("DELETE FROM public.chat_messages")


def postgres_history_store() -> PostgresHistoryStore | None:
    return PostgresHistoryStore(settings.database_url) if settings.database_url else None
