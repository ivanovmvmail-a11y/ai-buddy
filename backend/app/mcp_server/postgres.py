"""Прямой PostgreSQL: один ленивый async-пул и атомарный unit of work."""
from contextlib import asynccontextmanager
import logging

from psycopg import sql
from .absence_models import AbsenceRequest
from psycopg.types.json import Jsonb
from app.db.pool import PostgresPoolOwner

from .errors import Conflict
from .models import (AccessRequest, AccessResource, ActionDraft, Event, InternState, OnboardingData,
                     PlanItem, Reminder, SkillProfile, CatalogItem)

# Порядок соответствует внешним ключам; SQL-имена определены кодом, не вводом пользователя.
TABLES = (
    ("drafts", "service_drafts", ActionDraft, "id"),
    ("interns", "intern_state", InternState, "intern_id"),
    ("resources", "access_resources", AccessResource, "id"),
    ("personal_catalog", "personal_catalog", CatalogItem, "key"),
    ("items", "plan_items", PlanItem, "id"),
    ("absence_requests", "absence_requests", AbsenceRequest, "id"),
    ("requests", "access_requests", AccessRequest, "id"),
    ("profiles", "skill_profiles", SkillProfile, "intern_id"),
    ("reminders", "reminders", Reminder, "id"),
)
JSON_FIELDS = {"fields", "skills", "strengths", "growth", "payload"}
DERIVED_FIELDS = {"overdue", "waiting_days", "skill_level", "in_plan"}
OPTIONAL_TABLES = {"service_drafts", "mentor_questions", "absence_requests", "self_check_attempts"}
log = logging.getLogger("ai_buddy.onboarding")
LOCK_ID = 101003  # Общая блокировка записи/seed/reset онбординга, включая другие процессы.


def _dump(model):
    return model.model_dump(mode="json", exclude=DERIVED_FIELDS)


class PostgresStore(PostgresPoolOwner):
    def __init__(self, database_url):
        super().__init__(database_url)
        self._missing_warned = set()

    async def _available_tables(self, connection):
        cursor = await connection.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public'")
        available = {row["tablename"] for row in await cursor.fetchall()}
        missing = {table for _, table, *_ in TABLES if table in OPTIONAL_TABLES and table not in available}
        if missing - self._missing_warned:
            log.warning("Дополнительные таблицы %s пока не созданы: примените новые миграции. Основной онбординг продолжает работать в PostgreSQL.", ", ".join(sorted(missing)))
            self._missing_warned.update(missing)
        return available

    async def _load(self, connection, *, include_events):
        data = OnboardingData()
        available = await self._available_tables(connection)
        for field, table, model, key in TABLES:
            if table in OPTIONAL_TABLES and table not in available:
                continue
            cursor = await connection.execute(sql.SQL("SELECT * FROM {} ORDER BY seq").format(
                sql.Identifier("public", table)))
            for row in await cursor.fetchall():
                row.pop("seq")  # Порядок хранения — не часть публичной модели.
                if model is PlanItem:
                    row["waiting_days"] = 0 if row["status"] == "waiting" else None
                record = model.model_validate(row)
                getattr(data, field)[getattr(record, key)] = record
        if include_events:
            cursor = await connection.execute("SELECT ts, user_id, role, team, type, payload FROM public.events ORDER BY id")
            data.events = [Event.model_validate(row) for row in await cursor.fetchall()]
        return data

    @staticmethod
    def _baseline(data):
        return {field: {key: _dump(value) for key, value in getattr(data, field).items()}
                for field, *_ in TABLES}

    async def _insert_events(self, connection, events):
        if not events:
            return
        async with connection.cursor() as cursor:
            await cursor.executemany(
                "INSERT INTO public.events (ts, user_id, role, team, type, payload) VALUES (%s,%s,%s,%s,%s,%s)",
                [(event.ts, event.user_id, str(event.role), event.team, event.type, Jsonb(event.payload)) for event in events],
            )

    async def _save(self, connection, data, baseline, *, missing_ok=False):
        available = await self._available_tables(connection)
        for field, table, _, key_column in reversed(TABLES):
            if table in OPTIONAL_TABLES and table not in available:
                continue
            removed = set(baseline[field]) - set(getattr(data, field))
            for key in removed:
                await connection.execute(sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                    sql.Identifier("public", table), sql.Identifier(key_column)), (key,))
        cursor = await connection.execute("SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='reminders'")
        reminder_columns = {row["column_name"] for row in await cursor.fetchall()}
        for field, table, _, key_column in TABLES:
            if table in OPTIONAL_TABLES and table not in available:
                if getattr(data, field) and not missing_ok:
                    raise Conflict("Сервис пока недоступен: примените новые миграции базы данных")
                continue
            for key, record in getattr(data, field).items():
                values = _dump(record)
                if baseline[field].get(key) == values:
                    continue
                if table == "reminders" and "mentor_questions" not in available:
                    if values.pop("mentor_question_id", None) is not None:
                        raise Conflict("Сервис пока недоступен: примените новые миграции базы данных")
                if table == "reminders":
                    unavailable = set(values) - reminder_columns
                    if unavailable and record.kind not in {"plan_item", "access_request"}:
                        raise Conflict("Уведомления пока недоступны: примените новые миграции базы данных")
                    values = {key: value for key, value in values.items() if key in reminder_columns}
                columns = list(values)
                query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT ({}) DO UPDATE SET {}").format(
                    sql.Identifier("public", table),
                    sql.SQL(",").join(map(sql.Identifier, columns)),
                    sql.SQL(",").join(sql.Placeholder() for _ in columns),
                    sql.Identifier(key_column),
                    sql.SQL(",").join(sql.SQL("{} = EXCLUDED.{}").format(sql.Identifier(name), sql.Identifier(name))
                                      for name in columns if name != key_column),
                )
                await connection.execute(query, tuple(Jsonb(values[name]) if (name in JSON_FIELDS or (table == "reminders" and name == "action")) and values[name] is not None else values[name]
                                                      for name in columns))

    @asynccontextmanager
    async def transaction(self, *, include_events=True, copy_on_commit=True):
        # SQL уже отделяет возвращаемые модели от сохранённых строк; copy_on_commit
        # сохраняется для совместимости с InMemoryStore, в PostgreSQL копия не нужна.
        async with (await self._get_pool()).connection() as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            data = await self._load(connection, include_events=include_events)
            baseline = self._baseline(data)
            old_events = [_dump(event) for event in data.events]
            yield data
            await self._save(connection, data, baseline)
            if include_events and [_dump(event) for event in data.events[:len(old_events)]] != old_events:
                # Явная замена/очистка журнала (reset), а не обычный append.
                await connection.execute("DELETE FROM public.events")
                await self._insert_events(connection, data.events)
            else:
                await self._insert_events(connection, data.events[len(old_events):])

    @asynccontextmanager
    async def read(self, *, include_events=False):
        async with (await self._get_pool()).connection() as connection:
            # Несколько SELECT видят один согласованный снимок, даже при сбросе демо.
            await connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            data = await self._load(connection, include_events=include_events)
            count = len(data.events)
            yield data
            if include_events and len(data.events) != count:
                raise RuntimeError("Historical reads must not append events")
            await self._insert_events(connection, data.events[count:])

    async def seed_for_schema(self, data):
        """Сброс основного демо не требует ещё не созданных таблиц бонусов."""
        async with (await self._get_pool()).connection() as connection:
            available = await self._available_tables(connection)
        return data.model_copy(update={field: {} for field, table, *_ in TABLES
                                       if table in OPTIONAL_TABLES and table not in available})

    async def initialize(self, data, *, reset=False):
        async with (await self._get_pool()).connection() as connection:
            await connection.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK_ID,))
            available = await self._available_tables(connection)
            active_tables = [table for _, table, *_ in TABLES if table not in OPTIONAL_TABLES or table in available]
            cursor = await connection.execute(sql.SQL("SELECT EXISTS ({}) AS populated").format(
                sql.SQL(" UNION ALL ").join(sql.SQL("SELECT 1 FROM {}").format(sql.Identifier("public", table))
                                             for table in [name for name in active_tables if name != "personal_catalog"] + ["events"])))
            populated = (await cursor.fetchone())["populated"]
            if populated and not reset:
                return
            if reset:
                await connection.execute("DELETE FROM public.events")
                for _, table, *_ in reversed(TABLES):
                    if table in OPTIONAL_TABLES and table not in available:
                        continue
                    await connection.execute(sql.SQL("DELETE FROM {}").format(sql.Identifier("public", table)))
            await self._save(connection, data, {field: {} for field, *_ in TABLES}, missing_ok=True)
            await self._insert_events(connection, data.events)
