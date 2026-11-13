"""Ревью #70: нейтральные понижения, один актуальный факт и явное добавление."""
import pytest
import psycopg
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, clock, hiring, storage
from app.mcp_server.models import Reminder
from app.mcp_server.postgres import PostgresStore
from app.mcp_server.seed import load_seed
from .test_skill_suggestions import A, P, suggestions
from .test_notifications import own

run = async_runner.run


def explicit_add(store, actor, intern_id, key):
    # Доверенный обработчик каталога #71 вызывает этот hook после проверки прав.
    async def add():
        async with store.transaction(include_events=False, copy_on_commit=False) as data:
            return checklist._add_personal(data, actor, intern_id, data.personal_catalog[key],
                reason='добавил наставник').model_copy(deep=True)
    return run(add())


@pytest.mark.parametrize('before,after', [('familiar','novice'), ('confident','novice'), ('confident','familiar')])
def test_lowering_is_neutral_and_does_not_double_notify(store, edit, snapshot, before, after):
    def prepare(data):
        data.profiles[A.id].skills['git'] = before
        data.items.pop('anya.p.git')
    edit(prepare)
    run(hiring.set_skill_level(P, A.id, 'git', after))
    notices = own(A)
    assert len(notices) == 1
    notice = notices[0]
    assert notice.kind == 'skill_changed' and notice.action.target == 'plan'
    assert notice.action.topic == 'git'
    assert 'Git' in notice.text and 'обновил' in notice.text
    assert all(word not in notice.text for word in ('новичок', 'слаб', 'Наставник отметил', 'знаком'))
    assert ('anya.p.git' in snapshot().items) == (after == 'novice')
    assert not any(r.kind == 'personal_item_added' for r in notices)


@pytest.mark.parametrize('old_status', ['active', 'snoozed', 'done'])
def test_only_latest_fact_for_topic_is_active_and_snooze_cannot_restore_old_level(store, snapshot, old_status):
    run(hiring.set_skill_level(P, A.id, 'git', 'familiar'))
    first = own(A)[0]
    assert 'Git — знаком' in first.text
    if old_status == 'snoozed':
        run(clock.snooze_reminder(A, first.id, 3))
    elif old_status == 'done':
        run(clock.done_reminder(A, first.id))
    run(hiring.set_skill_level(P, A.id, 'sql', 'familiar'))
    sql = next(r for r in own(A) if r.action.topic == 'sql')
    kirill = DEMO_USERS['intern-kirill']
    run(hiring.set_skill_level(P, kirill.id, 'git', 'familiar'))
    other = own(kirill)[0]
    run(hiring.set_skill_level(P, A.id, 'git', 'confident'))
    state = snapshot()
    assert state.reminders[first.id].status == 'done'
    assert state.reminders[first.id].snooze_until_day is None
    assert state.reminders[sql.id].status == 'active'
    assert state.reminders[other.id].status == 'active'
    current = [r for r in own(A) if r.kind == 'skill_changed' and r.action.topic == 'git' and r.status == 'active']
    assert len(current) == 1 and current[0].id != first.id
    assert 'Git — уверенно' in current[0].text
    for _ in range(3): run(clock.advance_day(A, A.id))
    assert snapshot().reminders[first.id].status == 'done'
    before = snapshot()
    run(hiring.set_skill_level(P, A.id, 'git', 'confident'))
    assert snapshot() == before


def test_explicit_catalog_add_notifies_once_and_removal_preserves_history(store, snapshot):
    assert own(A) == []
    item = explicit_add(store, P, A.id, 'platform.testing')
    notice = own(A)[0]
    assert notice.kind == 'personal_item_added' and notice.plan_item_id == item.id
    assert 'добавил наставник' in notice.text
    assert notice.action.target == 'plan_item'
    async def remove():
        async with store.transaction(include_events=False, copy_on_commit=False) as data:
            checklist._remove_personal(data, P, data.items[item.id])
    run(remove())
    assert snapshot().reminders[notice.id].status == 'done'
    assert snapshot().reminders[notice.id].plan_item_id is None
    # Seed/пересборка не выдают себя за явное добавление наставником.
    assert not load_seed().reminders


def test_rebuild_multiple_topics_has_no_personal_notices_and_nonmentor_hook_does_not_notify(store):
    run(hiring.set_skill_level(P, A.id, 'testing', 'novice'))
    assert [r.kind for r in own(A)] == ['skill_changed']
    explicit_add(store, A, A.id, 'platform.sql')
    assert [r.kind for r in own(A)] == ['skill_changed']


def test_accept_keeps_main_fixes_and_emits_only_one_result(store, snapshot):
    run(hiring.mark_known(A, 'anya.p.git'))
    s = suggestions()[0]
    result = run(hiring.decide_suggestion(P, s.id, True))
    assert result.status == 'accepted'
    decisions = [e for e in snapshot().events if e.type == 'skill_suggestion_decided']
    assert [e.payload['status'] for e in decisions] == ['accepted']
    assert len(own(A)) == 1 and 'Git — знаком' in own(A)[0].text
    assert next(r for r in own(P) if r.suggestion_id == s.id).status == 'done'
    creation = next(e for e in snapshot().events if e.type == 'skill_suggestion_created')
    assert creation.user_id == 'system'


def test_topic_metadata_survives_restart_and_deduplicates_in_postgres(onboarding_dsn, monkeypatch):
    first = PostgresStore(onboarding_dsn)
    monkeypatch.setattr(storage, 'get_store', lambda: first)
    run(first.initialize(load_seed(), reset=True))
    run(hiring.set_skill_level(P, A.id, 'git', 'familiar'))
    old = own(A)[0]
    run(first.close())
    second = PostgresStore(onboarding_dsn)
    monkeypatch.setattr(storage, 'get_store', lambda: second)
    try:
        assert own(A)[0].action.topic == 'git'
        run(hiring.set_skill_level(P, A.id, 'git', 'confident'))
        assert next(r for r in own(A) if r.id == old.id).status == 'done'
        assert len([r for r in own(A) if r.status == 'active']) == 1
        with psycopg.connect(onboarding_dsn) as connection:
            assert connection.execute("SELECT action->>'topic', status FROM reminders WHERE id=%s", (old.id,)).fetchone() == ('git','done')
    finally:
        run(second.close())


def test_old_action_without_topic_is_still_serialized_in_old_shape():
    old = Reminder(id='old', user_id=A.id, created_day=1, text='Демо',
                   action={'label':'Открыть','target':'plan'})
    assert old.action.topic is None
    assert old.model_dump()['action'] == {'label':'Открыть','target':'plan'}
