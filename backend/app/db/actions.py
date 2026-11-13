"""Черновики действий в PostgreSQL (SPEC §9; Claude 13.11) — протокол `app.agent.actions.ActionStore`.

Таблица — миграция `20261113130000_chat_and_actions.sql`. Адаптер для `app.agent.service.make_action_store`.
"""
from typing import Any

from psycopg.types.json import Jsonb

from app.agent.actions import Action, InMemoryActionStore, _now, new_action
from app.config import settings

from ._table import _TableOrMemory

_COLUMNS = "id, user_id, tool, title, params, status, result, error, created_at, updated_at"
_UPSERT = (f"INSERT INTO public.agent_actions ({_COLUMNS}) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
           "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, result = EXCLUDED.result, "
           "error = EXCLUDED.error, title = EXCLUDED.title, params = EXCLUDED.params, updated_at = EXCLUDED.updated_at "
           f"RETURNING {_COLUMNS}")


def _row(action: Action) -> tuple:
    values = action.model_dump(mode="json")
    return (action.id, action.user_id, action.tool, action.title, Jsonb(values["params"]), action.status,
            Jsonb(values["result"]) if values["result"] is not None else None, action.error,
            action.created_at, action.updated_at)


class PostgresActionStore(_TableOrMemory):
    table = "agent_actions"

    def __init__(self, database_url: str) -> None:
        super().__init__(database_url, InMemoryActionStore())

    async def _one(self, query: str, args: tuple) -> Action | None:
        async with (await self._get_pool()).connection() as connection:
            row = await (await connection.execute(query, args)).fetchone()
        return Action.model_validate(row) if row else None

    async def create(self, *, user_id: str, tool: str, title: str, params: dict[str, Any]) -> Action:
        if not await self._use_db():
            return await self._fallback.create(user_id=user_id, tool=tool, title=title, params=params)
        return await self._one(_UPSERT, _row(new_action(user_id=user_id, tool=tool, title=title, params=params)))

    async def get(self, action_id: str) -> Action | None:
        if not await self._use_db():
            return await self._fallback.get(action_id)
        return await self._one(f"SELECT {_COLUMNS} FROM public.agent_actions WHERE id = %s", (action_id,))

    async def list_for(self, user_id: str) -> list[Action]:
        if not await self._use_db():
            return await self._fallback.list_for(user_id)
        async with (await self._get_pool()).connection() as connection:
            rows = await (await connection.execute(
                f"SELECT {_COLUMNS} FROM public.agent_actions WHERE user_id = %s ORDER BY created_at DESC",
                (user_id,))).fetchall()
        return [Action.model_validate(row) for row in rows]

    async def save(self, action: Action) -> Action:
        if not await self._use_db():
            return await self._fallback.save(action)
        action.updated_at = _now()
        await self._one(_UPSERT, _row(action))
        return action

    async def claim(self, action_id: str, user_id: str) -> Action | None:
        """Атомарно: из одновременных «Подтвердить» выполняет один (аудит D1) — одна команда UPDATE … WHERE pending."""
        if not await self._use_db():
            return await self._fallback.claim(action_id, user_id)
        return await self._one(
            "UPDATE public.agent_actions SET status = 'running', updated_at = now() "
            f"WHERE id = %s AND user_id = %s AND status = 'pending' RETURNING {_COLUMNS}", (action_id, user_id))

    async def clear(self) -> None:
        if not await self._use_db():
            return await self._fallback.clear()
        async with (await self._get_pool()).connection() as connection:
            await connection.execute("DELETE FROM public.agent_actions")


def postgres_action_store() -> PostgresActionStore | None:
    return PostgresActionStore(settings.database_url) if settings.database_url else None
