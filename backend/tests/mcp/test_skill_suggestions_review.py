"""Ревью #68: отложенная миграция, отсутствующий DEMO_USER и жизненный цикл."""
import pytest
import psycopg

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, hiring, storage
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import Conflict, NotFound
from app.mcp_server.models import Reminder
from app.mcp_server.postgres import PostgresStore
from app.mcp_server.seed import load_seed

from .conftest import MIGRATION
from .test_bonus_schema_compat import old_database
from .test_skill_suggestions import A, P, suggestions

run = async_runner.run


@pytest.mark.parametrize('populated', [False, True])
def test_missing_suggestions_table_keeps_progress_in_postgres_and_recovers_live(
    onboarding_dsn, monkeypatch, caplog, populated
):
    with old_database(onboarding_dsn) as dsn:
        with psycopg.connect(dsn, autocommit=True) as connection:
            for name in ('20261111120000_service_drafts.sql', '20261111120200_absence.sql',
                         '20261111161000_reminder_kinds.sql'):
                connection.execute(MIGRATION.with_name(name).read_text(encoding='utf-8'))
        primary = PostgresStore(dsn)
        demo = storage.DemoStore(primary)
        monkeypatch.setattr(storage, 'get_store', lambda: demo)
        try:
            if populated:
                run(primary.initialize(load_seed()))
                with psycopg.connect(dsn, autocommit=True) as connection:
                    connection.execute("UPDATE intern_state SET current_day=4 WHERE intern_id=%s", (A.id,))
            plan = run(checklist.get_plan(A, A.id))
            assert plan.current_day == (4 if populated else 2)
            assert demo._store is primary
            run(checklist.set_item_status(A, 'anya.w1.notes', 'done'))
            run(checklist.set_item_status(A, 'anya.p.git', 'done'))
            marked = run(hiring.mark_known(A, 'anya.w1.notes'))
            assert marked.known_marked and marked.status == 'done'
            request = run(access.create_request(A, 'bitbucket-platform', 'read', 'Учебная задача'))
            assert run(access.decide_request(P, request.id, True)).status == 'granted'
            assert suggestions() == []
            assert demo._store is primary
            assert 'skill_suggestions' in caplog.text and 'PostgreSQL' in caplog.text
            assert 'InMemoryStore' not in caplog.text
            with psycopg.connect(dsn, autocommit=True) as connection:
                assert connection.execute("SELECT to_regclass('public.skill_suggestions')").fetchone() == (None,)
                assert connection.execute("SELECT status FROM plan_items WHERE id='anya.p.git'").fetchone() == ('done',)
                assert connection.execute("SELECT status FROM access_requests WHERE id=%s", (request.id,)).fetchone() == ('granted',)
                assert connection.execute("SELECT count(*) FROM events WHERE type='skill_suggestion_created'").fetchone() == (0,)
                connection.execute(MIGRATION.with_name('20261111162000_skill_suggestions.sql').read_text(encoding='utf-8'))
            # Та же фабрика/пул, миграция применяется после автодеплоя, без рестарта.
            run(hiring.mark_known(A, 'anya.p.ci'))
            assert [s.topic for s in suggestions()] == ['ci']
            assert demo._store is primary
            assert sum('skill_suggestions' in r.getMessage() for r in caplog.records) == 1
        finally:
            run(demo.close())


def _orphan_state(data, id='intern-not-registered'):
    data.interns[id] = data.interns[A.id].model_copy(update={'intern_id': id})
    data.profiles[id] = data.profiles[A.id].model_copy(update={'intern_id': id})
    return id


def test_unknown_seed_intern_does_not_rollback_item_completion(store, snapshot):
    async def complete():
        async with store.transaction(include_events=False, copy_on_commit=False) as data:
            id = _orphan_state(data)
            assert id not in DEMO_USERS
            for suffix in ('first', 'second'):
                item = data.items['anya.p.git'].model_copy(update={
                    'id': f'orphan.{suffix}', 'intern_id': id, 'catalog_key': None,
                }, deep=True)
                data.items[item.id] = item
                checklist._change_status(data, SYSTEM_ACTOR, item, 'done')
    run(complete())
    data = snapshot()
    assert data.items['orphan.second'].status == 'done'
    assert data.suggestions == {}
    assert len([e for e in data.events if e.type == 'plan_item_status_changed'
                and e.payload['intern_id'] == 'intern-not-registered']) == 2


def test_unknown_seed_intern_is_skipped_by_view_and_mentor_list(store, edit, snapshot):
    run(hiring.mark_known(A, 'anya.p.git'))
    visible = suggestions()[0]
    def orphan(data):
        id = _orphan_state(data)
        data.suggestions['orphan'] = data.suggestions[visible.id].model_copy(
            update={'id': 'orphan', 'intern_id': id}, deep=True)
    edit(orphan)
    data = snapshot()
    assert hiring._suggestion_view(data, data.suggestions['orphan']) is None
    assert [s.id for s in run(hiring.list_suggestions(P, status=None))] == [visible.id]
    with pytest.raises(NotFound):
        run(hiring.decide_suggestion(P, 'orphan', True))


def test_manual_level_change_dismisses_only_same_topic_and_frees_pending_slot(store, edit, snapshot):
    run(hiring.mark_known(A, 'anya.p.git'))
    run(hiring.mark_known(A, 'anya.p.ci'))
    old = next(s for s in suggestions() if s.topic == 'git')
    def remind(data):
        data.suggestions['other-intern'] = data.suggestions[old.id].model_copy(update={
            'id': 'other-intern', 'intern_id': 'intern-ivan', 'mentor_id': 'mentor-maria',
        }, deep=True)
        data.reminders['proposal'] = Reminder(id='proposal', user_id=P.id,
            suggestion_id=old.id, intern_id=A.id, kind='skill_suggestion', text='Демо',
            created_day=2, status='snoozed', snooze_until_day=3)
        ci = next(s for s in data.suggestions.values() if s.topic == 'ci')
        data.reminders['other-topic'] = Reminder(id='other-topic', user_id=P.id,
            suggestion_id=ci.id, intern_id=A.id, kind='skill_suggestion', text='Демо CI', created_day=2)
    edit(remind)
    run(hiring.set_skill_level(P, A.id, 'git', 'familiar'))
    data = snapshot()
    assert data.suggestions[old.id].status == 'dismissed'
    assert data.suggestions['other-intern'].status == 'pending'
    assert data.suggestions[old.id].decided_day == 2
    assert data.reminders['proposal'].status == 'done'
    assert data.reminders['proposal'].snooze_until_day is None
    assert data.reminders['other-topic'].status == 'active'
    assert [s.topic for s in suggestions()] == ['ci']
    decisions = [e for e in data.events if e.type == 'skill_suggestion_decided']
    assert len(decisions) == 1 and decisions[0].user_id == P.id
    assert decisions[0].payload['cause'] == 'manual_skill_change'
    run(hiring.mark_known(A, 'anya.w1.notes'))
    new = next(s for s in suggestions() if s.topic == 'git')
    assert new.from_level == 'familiar' and new.to_level == 'confident'
    assert new.id != old.id
    before = snapshot()
    run(hiring.set_skill_level(P, A.id, 'git', 'familiar'))
    assert snapshot() == before


def test_accept_does_not_emit_a_dismissal_and_external_stale_profile_still_conflicts(store, edit, snapshot):
    run(hiring.mark_known(A, 'anya.p.git'))
    s = suggestions()[0]
    edit(lambda data: data.profiles[A.id].skills.update(git='confident'))
    with pytest.raises(Conflict):
        run(hiring.decide_suggestion(P, s.id, True))
    assert snapshot().suggestions[s.id].status == 'pending'
    edit(lambda data: data.profiles[A.id].skills.update(git='novice'))
    run(hiring.decide_suggestion(P, s.id, True))
    assert snapshot().suggestions[s.id].status == 'accepted'
    assert [e.payload['status'] for e in snapshot().events if e.type == 'skill_suggestion_decided'] == ['accepted']


@pytest.mark.parametrize('count,phrase', [
    (1, 'закрыт 1 пункт'), (2, 'закрыто 2 пункта'), (4, 'закрыто 4 пункта'),
    (5, 'закрыто 5 пунктов'), (11, 'закрыто 11 пунктов'), (12, 'закрыто 12 пунктов'),
    (14, 'закрыто 14 пунктов'), (21, 'закрыт 21 пункт'), (22, 'закрыто 22 пункта'),
    (25, 'закрыто 25 пунктов'), (111, 'закрыто 111 пунктов'),
])
def test_russian_basis_pluralization(count, phrase):
    assert hiring._closed_basis(count, 'Git') == f'{phrase} по теме Git'


@pytest.mark.parametrize('count,expected', [(2, 'закрыто 2 пункта'), (5, 'закрыто 5 пунктов'), (21, 'закрыт 21 пункт')])
def test_basis_and_system_actor_on_real_completion(store, edit, snapshot, count, expected):
    def prepare(data):
        for n in range(count-1):
            item = data.items['anya.p.git'].model_copy(update={
                'id': f'anya.done.{n}', 'catalog_key': None, 'status': 'done',
            }, deep=True)
            data.items[item.id] = item
    edit(prepare)
    run(checklist.set_item_status(A, 'anya.p.git', 'done'))
    assert suggestions()[0].basis == f'{expected} по теме Git'
    created = [e for e in snapshot().events if e.type == 'skill_suggestion_created']
    assert len(created) == 1
    event = created[0]
    assert (event.user_id, event.role, event.team) == ('system', 'system', 'system')
    assert event.payload['intern_id'] == A.id and event.payload['day'] == 2


def test_nonintern_seed_row_is_not_assessed_or_exposed_as_student(store, edit, monkeypatch, snapshot):
    from app.agent.users import Role, User
    invalid = User(id='not-an-intern', role=Role.LEAD, name='Демо', team=A.team, mentor_id=P.id)
    monkeypatch.setitem(DEMO_USERS, invalid.id, invalid)
    run(hiring.mark_known(A, 'anya.p.git'))
    visible = suggestions()[0]
    def invalid_seed(data):
        _orphan_state(data, invalid.id)
        for suffix in ('first', 'second'):
            item = data.items['anya.p.git'].model_copy(update={
                'id': f'invalid.{suffix}', 'intern_id': invalid.id, 'catalog_key': None,
            }, deep=True)
            data.items[item.id] = item
            checklist._change_status(data, SYSTEM_ACTOR, item, 'done')
        assert len(data.suggestions) == 1
        data.suggestions['invalid-role'] = data.suggestions[visible.id].model_copy(update={
            'id': 'invalid-role', 'intern_id': invalid.id,
        }, deep=True)
    edit(invalid_seed)
    assert [s.id for s in run(hiring.list_suggestions(P))] == [visible.id]
    assert snapshot().items['invalid.second'].status == 'done'
    with pytest.raises(NotFound):
        run(hiring.decide_suggestion(P, 'invalid-role', True))
