"""Ревью #71: ручное решение наставника сохраняется, id остаётся стабильным."""
import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, hiring
from app.mcp_server.errors import Conflict
from .test_skill_suggestions import A, P, suggestions

run = async_runner.run


def test_manual_sql_survives_familiar_novice_and_confident_and_is_removed_only_explicitly(store, snapshot):
    assert snapshot().profiles[A.id].skills['sql'] == 'confident'
    item = run(checklist.add_personal_item(P, A.id, 'platform.sql'))
    original = snapshot().items[item.id]
    for level in ['familiar', 'novice', 'confident']:
        run(hiring.set_skill_level(P, A.id, 'sql', level))
        assert snapshot().items[item.id] == original
        view = next(i for i in run(checklist.get_plan(P, A.id)).items if i.id == item.id)
        assert view.reason == 'добавил наставник' and view.skill_level == level
        assert view.status == 'not_started'
    assert len([r for r in snapshot().reminders.values() if r.kind == 'personal_item_added']) == 1
    assert not any(e.type == 'personal_item_removed' and e.payload['item_id'] == item.id for e in snapshot().events)
    run(checklist.remove_personal_item(P, item.id))
    assert item.id not in snapshot().items


def test_auto_points_still_rebuild_only_changed_topic_and_accept_is_not_dismissed(store, snapshot):
    manual = run(checklist.add_personal_item(P, A.id, 'platform.sql'))
    run(checklist.remove_personal_item(P, 'anya.p.git'))
    run(hiring.set_skill_level(P, A.id, 'ci', 'familiar'))
    assert 'anya.p.ci' not in snapshot().items
    assert 'anya.p.git' not in snapshot().items
    assert manual.id in snapshot().items
    # Возвращаем novice только в изменённой CI: Git, снятый наставником, не возвращается.
    run(hiring.set_skill_level(P, A.id, 'ci', 'novice'))
    assert 'anya.p.ci' in snapshot().items and 'anya.p.git' not in snapshot().items
    run(hiring.mark_known(A, 'anya.p.ci'))
    s = next(s for s in suggestions() if s.topic == 'ci')
    result = run(hiring.decide_suggestion(P, s.id, True))
    assert result.status == 'accepted'
    assert 'anya.p.ci' not in snapshot().items and manual.id in snapshot().items
    decisions = [e for e in snapshot().events if e.type == 'skill_suggestion_decided' and e.payload['suggestion_id'] == s.id]
    assert [e.payload['status'] for e in decisions] == ['accepted']
    assert 'anya.p.git' not in snapshot().items


@pytest.mark.parametrize('intern_id,mentor_id,key,expected', [
    ('intern-anya', 'mentor-petr', 'platform.testing', 'anya.p.testing'),
    ('intern-kirill', 'mentor-petr', 'platform.git', 'kirill.p.git'),
    ('intern-ivan', 'mentor-maria', 'delivery.git', 'ivan.p.git'),
    ('intern-liza', 'mentor-maria', 'delivery.sql', 'liza.p.sql'),
])
def test_catalog_add_duplicate_remove_and_readd_share_stable_id(store, snapshot, intern_id, mentor_id, key, expected):
    mentor = DEMO_USERS[mentor_id]
    added = run(checklist.add_personal_item(mentor, intern_id, key))
    assert added.id == expected
    with pytest.raises(Conflict):
        run(checklist.add_personal_item(mentor, intern_id, key))
    assert snapshot().items[expected].catalog_key == key
    run(checklist.remove_personal_item(mentor, expected))
    assert expected not in snapshot().items
    readded = run(checklist.add_personal_item(mentor, intern_id, key))
    assert readded.id == expected and readded.reason == 'добавил наставник'


def test_manual_assignment_survives_level_change_after_restart(onboarding_dsn, monkeypatch):
    from app.mcp_server import storage
    from app.mcp_server.postgres import PostgresStore
    from app.mcp_server.seed import load_seed
    first = PostgresStore(onboarding_dsn)
    monkeypatch.setattr(storage, 'get_store', lambda: first)
    run(first.initialize(load_seed(), reset=True))
    item = run(checklist.add_personal_item(P, A.id, 'platform.sql'))
    run(first.close())
    second = PostgresStore(onboarding_dsn)
    monkeypatch.setattr(storage, 'get_store', lambda: second)
    try:
        run(hiring.set_skill_level(P, A.id, 'sql', 'familiar'))
        plan = run(checklist.get_plan(P, A.id))
        assert next(i for i in plan.items if i.id == item.id).reason == 'добавил наставник'
        run(checklist.remove_personal_item(P, item.id))
        assert item.id not in {i.id for i in run(checklist.get_plan(P, A.id)).items}
    finally:
        run(second.close())
