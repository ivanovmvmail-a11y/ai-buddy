import json
from pathlib import Path

import pytest
from app import async_runner
from app.agent.users import DEMO_USERS, User, Role
from app.mcp_server import checklist, hiring
from app.mcp_server.errors import NotFound
from app.mcp_server.seed import load_seed

run = async_runner.run
A = DEMO_USERS['intern-anya']
P = DEMO_USERS['mentor-petr']


def test_catalog_scope_and_permissions_for_every_demo_user(store):
    catalog = run(checklist.list_catalog(P, A.id))
    assert len(catalog) == 4
    assert all(e.team == A.team for e in catalog)
    assert {e.topic for e in catalog if e.in_plan} == {'git', 'ci'}
    for user in DEMO_USERS.values():
        if user.id != P.id:
            for target in [A.id, 'missing']:
                with pytest.raises(NotFound, match='^Не найдено$'):
                    run(checklist.list_catalog(user, target))
    catalog[0].title = 'mutated'
    assert run(checklist.list_catalog(P, A.id))[0].title != 'mutated'


def test_rebuild_preserves_common_and_done_and_removes_pending(store, snapshot):
    before = {k: v for k, v in snapshot().items.items() if v.kind == 'common'}
    run(checklist.set_item_status(A, 'anya.p.ci', 'done'))
    run(hiring.set_skill_level(P, A.id, 'ci', 'confident'))
    assert snapshot().items['anya.p.ci'].status == 'done'
    run(hiring.set_skill_level(P, A.id, 'git', 'familiar'))
    assert 'anya.p.git' not in snapshot().items
    run(hiring.set_skill_level(P, A.id, 'git', 'novice'))
    new = snapshot().items['anya.p.git']
    assert new.kind == 'personal' and 'Git — новичок' in new.reason
    assert {k:v for k,v in snapshot().items.items() if v.kind == 'common'} == before
    run(hiring.set_skill_level(P, A.id, 'git', 'novice'))
    assert len([v for v in snapshot().items.values() if v.id == new.id]) == 1
    plan = run(checklist.get_plan(A, A.id))
    assert next(i for i in plan.items if i.id == 'anya.w1.notes').skill_level == 'novice'
    events = [e for e in snapshot().events if e.type == 'personal_item_removed']
    assert events and 'title' not in events[-1].payload


def test_reminder_fk_is_detached_when_personal_item_removed(store, edit, snapshot):
    from app.mcp_server.models import Reminder
    def add(data):
        data.reminders['personal'] = Reminder(id='personal', user_id=A.id,
            plan_item_id='anya.p.git', text='demo', created_day=2)
    edit(add)
    run(hiring.set_skill_level(P, A.id, 'git', 'confident'))
    assert snapshot().reminders['personal'].plan_item_id is None
    assert snapshot().reminders['personal'].status == 'done'


def test_two_new_seed_interns_without_changing_agent(monkeypatch):
    for uid, mentor, lead, team in [('kirill','petr','olga',A.team), ('liza','maria','sergey',DEMO_USERS['intern-ivan'].team)]:
        user = User(id=f'intern-{uid}',name=uid,role=Role.INTERN,team=team,
                    mentor_id=f'mentor-{mentor}',lead_id=f'lead-{lead}')
        monkeypatch.setitem(DEMO_USERS,user.id,user)
    data = load_seed()
    for uid, expected in [('intern-kirill','sql'),('intern-liza','git')]:
        assert data.interns[uid].current_day == 3
        assert [v.topic for v in data.items.values() if v.intern_id == uid and v.kind == 'personal'] == [expected]
    for a,b in [('anya','kirill'),('ivan','liza')]:
        def skeleton(prefix):
            return {i.id.split('.',1)[1]: i.title for i in data.items.values() if i.intern_id == f'intern-{prefix}' and i.kind == 'common'}
        assert skeleton(a) == skeleton(b)
    docs = Path(__file__).resolve().parents[2]/'app/rag/demo_docs'
    for entry in data.personal_catalog.values():
        assert (docs/entry.doc_source_id.removeprefix('demo:')).exists()


def test_new_seed_interns_persist_and_reset(store, monkeypatch):
    for uid, old in [('kirill','anya'),('liza','ivan')]:
        user=DEMO_USERS[f'intern-{old}'].model_copy(update={'id':f'intern-{uid}', 'name':uid})
        monkeypatch.setitem(DEMO_USERS,user.id,user)
    run(store.initialize(load_seed(),reset=True))
    assert run(checklist.get_plan(P,'intern-kirill')).intern_id == 'intern-kirill'
    run(hiring.set_skill_level(P,'intern-kirill','sql','confident'))
    assert not any(i.id=='kirill.p.sql' for i in run(checklist.get_plan(P,'intern-kirill')).items)


def test_catalog_and_rebuild_survive_store_restart(onboarding_dsn):
    from app.mcp_server.postgres import PostgresStore
    first=PostgresStore(onboarding_dsn)
    async def save():
        await first.initialize(load_seed(),reset=True)
        async with first.transaction() as data:
            data.profiles[A.id].skills['git']='confident'
            checklist._rebuild_personal(data,P,A.id)
        await first.close()
        second=PostgresStore(onboarding_dsn)
        try:
            async with second.read() as data:
                assert len(data.personal_catalog)==8
                assert 'anya.p.git' not in data.items
                assert data.items['anya.p.ci'].catalog_key=='platform.ci'
        finally:
            await second.close()
    run(save())


def test_upgrade_existing_database_preserves_progress(onboarding_dsn):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    from uuid import uuid4
    from .conftest import MIGRATION
    params=conninfo_to_dict(onboarding_dsn)
    name='catalog_upgrade_'+uuid4().hex[:12]
    with psycopg.connect(**{**params,'dbname':'postgres'},autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            with psycopg.connect(**{**params,'dbname':name},autocommit=True) as c:
                c.execute(MIGRATION.read_text(encoding='utf-8'))
                c.execute("INSERT INTO intern_state(intern_id,start_date,current_day) VALUES ('intern-anya','2026-11-10',4)")
                c.execute('''INSERT INTO skill_profiles(intern_id,skills,strengths,growth,updated_at)
                    VALUES ('intern-anya','{"git":"novice","sql":"confident"}','[]','[]',now())''')
                c.execute('''INSERT INTO plan_items(id,intern_id,stage,"order",title,summary,owner_role,status,updated_at)
                    VALUES ('anya.w1.notes','intern-anya','week1',7,'demo','demo','intern','done',now())''')
                old=c.execute("SELECT * FROM plan_items WHERE id='anya.w1.notes'").fetchone()
                c.execute(MIGRATION.with_name('20261111160000_personal_plan.sql').read_text(encoding='utf-8'))
                assert c.execute('SELECT count(*) FROM personal_catalog').fetchone()==(8,)
                assert c.execute("SELECT id FROM plan_items WHERE kind='personal'").fetchall()==[('anya.p.git',)]
                new=c.execute("SELECT * FROM plan_items WHERE id='anya.w1.notes'").fetchone()
                assert new[:len(old)]==old
                assert c.execute('SELECT current_day FROM intern_state').fetchone()==(4,)
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
