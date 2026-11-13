"""Общая часть хранилищ переписки и черновиков: таблица есть — PostgreSQL, нет — память процесса с предупреждением.

Модули хранилищ разнесены (`history.py`, `actions.py`), чтобы не было циклического импорта с `app.agent`: раньше
общий модуль тянул обе стороны, импорт молча падал, и переписка оставалась в памяти (найдено в Docker 13.11).
"""
import logging

from .pool import PostgresPoolOwner

log = logging.getLogger("ai_buddy.db")


class _TableOrMemory(PostgresPoolOwner):
    table = ""

    def __init__(self, database_url: str, fallback) -> None:
        super().__init__(database_url)
        self._fallback = fallback
        self._ready: bool | None = None  # None — ещё не проверяли

    async def _use_db(self) -> bool:
        if self._ready is None:
            async with (await self._get_pool()).connection() as connection:
                row = await (await connection.execute("SELECT to_regclass(%s) AS t", (f"public.{self.table}",))).fetchone()
            self._ready = row["t"] is not None
            if not self._ready:
                log.warning("Таблицы %s нет — примените миграцию 20261113130000_chat_and_actions.sql; "
                            "пока данные хранятся в памяти процесса.", self.table)
        return self._ready
