"""Автодеплой до дополнительных миграций сохраняет основной PostgreSQL-онбординг."""
from contextlib import contextmanager
from uuid import uuid4
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, clock, drafts, storage
from app.mcp_server.errors import Conflict
from app.mcp_server.models import Reminder
from app.mcp_server.postgres import PostgresStore, TABLES
from app.mcp_server.seed import load_seed
from .conftest import MIGRATION
run = async_runner.run

@contextmanager
def old_database(dsn):
    params = conninfo_to_dict(dsn)
    name = 'bonus_old_' + uuid4().hex
    with psycopg.connect(**{**params, 'dbname':'postgres'}, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            target = make_conninfo(**{**params,'dbname':name})
            with psycopg.connect(target,autocommit=True) as connection:
                connection.execute(MIGRATION.read_text())
            yield target
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_old_schema_stays_in_postgres_and_recovers_after_live_migration(onboarding_dsn,monkeypatch,caplog):
    with old_database(onboarding_dsn) as dsn:
        primary=PostgresStore(dsn)
        demo=storage.DemoStore(primary)
        monkeypatch.setattr(storage,'get_store',lambda:demo)
        try:
            plan=run(checklist.get_plan(DEMO_USERS['intern-anya'],'intern-anya'))
            assert demo._store is primary and plan.current_day==2
            run(checklist.set_item_status(DEMO_USERS['intern-anya'],'anya.w1.notes','done'))
            run(clock.advance_day(DEMO_USERS['intern-anya'],'intern-anya'))
            filtered = run(demo.seed_for_schema(load_seed()))
            assert not filtered.drafts
            async def reset_core():
                async with demo.transaction() as data:
                    for field in type(data).model_fields:
                        setattr(data, field, getattr(filtered, field))
            run(reset_core())
            run(checklist.set_item_status(DEMO_USERS['intern-anya'],'anya.w1.notes','done'))
            run(clock.advance_day(DEMO_USERS['intern-anya'],'intern-anya'))
            async def prepare():
                async with demo.transaction(include_events=False,copy_on_commit=False) as data:
                    return drafts.create(data,DEMO_USERS['intern-anya'],'test',{})
            with pytest.raises(Conflict,match='миграции'): run(prepare())
            assert demo._store is primary
            assert 'PostgreSQL' in caplog.text and 'service_drafts' in caplog.text
            with psycopg.connect(dsn,autocommit=True) as connection:
                assert connection.execute("SELECT status FROM plan_items WHERE id='anya.w1.notes'").fetchone()==('done',)
                # SQL приходит после автодеплоя; пул и процесс не перезапускаются.
                for pattern in ('*_service_drafts.sql','*_mentor_inbox.sql','*_absence.sql','*_self_check.sql'):
                    for path in sorted(MIGRATION.parent.glob(pattern)): connection.execute(path.read_text())
            draft=run(prepare())
            assert run(drafts.get_draft('intern-anya',draft.id)).status=='pending'
            assert run(checklist.get_plan(DEMO_USERS['intern-anya'],'intern-anya')).current_day==3
        finally: run(demo.close())


def test_seed_reset_and_base_reminder_writes_before_bonus_migration(onboarding_dsn):
    with old_database(onboarding_dsn) as dsn:
        store=PostgresStore(dsn)
        try:
            run(store.initialize(load_seed()))
            run(store.initialize(load_seed(),reset=True))
            async def mutate():
                async with store.transaction() as data:
                    data.reminders['legacy']=Reminder(id='legacy',user_id='intern-anya',text='Демо',created_day=2)
            run(mutate())
            with psycopg.connect(dsn) as connection:
                assert connection.execute("SELECT count(*) FROM reminders WHERE id='legacy'").fetchone()==(1,)
            if 'mentor_question_id' in Reminder.model_fields:
                async def unsupported():
                    async with store.transaction() as data:
                        data.reminders['unsupported']=Reminder(id='unsupported',user_id='mentor-petr',text='Демо',created_day=2,mentor_question_id='missing')
                with pytest.raises(Conflict,match='миграции'): run(unsupported())
        finally: run(store.close())
