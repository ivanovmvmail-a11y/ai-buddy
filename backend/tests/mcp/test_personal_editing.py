import asyncio
import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist,hiring
from app.mcp_server.errors import Conflict,Forbidden,NotFound
from .test_skill_suggestions import A,P
run=async_runner.run


def test_mentor_adds_and_removes_personal_without_affecting_common_or_profile(store,snapshot):
    before=snapshot()
    item=run(checklist.add_personal_item(P,A.id,'platform.sql'))
    assert item.kind=='personal' and item.reason=='добавил наставник' and item.skill_level=='confident'
    assert item.catalog_key=='platform.sql'
    assert snapshot().profiles==before.profiles
    assert next(e for e in run(checklist.list_catalog(P,A.id)) if e.key=='platform.sql').in_plan
    with pytest.raises(Conflict):run(checklist.add_personal_item(P,A.id,'platform.sql'))
    run(checklist.remove_personal_item(P,item.id))
    assert snapshot().items==before.items
    assert not next(e for e in run(checklist.list_catalog(P,A.id)) if e.key=='platform.sql').in_plan
    reminders=[r for r in snapshot().reminders.values() if r.kind=='personal_item_added']
    assert len(reminders)==1 and reminders[0].status=='done' and reminders[0].plan_item_id is None
    facts=[e for e in snapshot().events if e.type in {'personal_item_added','personal_item_removed'} and e.payload['item_id']==item.id]
    assert [e.type for e in facts]==['personal_item_added','personal_item_removed']
    assert all('title' not in e.payload and 'reason' not in e.payload for e in facts)
    with pytest.raises(NotFound):run(checklist.remove_personal_item(P,item.id))


@pytest.mark.parametrize('user_id',list(DEMO_USERS))
def test_edit_permissions_and_foreign_catalog_not_found(store,user_id):
    user=DEMO_USERS[user_id]
    if user_id!=P.id:
        with pytest.raises(NotFound):run(checklist.add_personal_item(user,A.id,'platform.sql'))
        for id in ['anya.p.git','missing']:
            with pytest.raises(NotFound):run(checklist.remove_personal_item(user,id))
    for key in ['delivery.sql','missing']:
        with pytest.raises(NotFound):run(checklist.add_personal_item(P,A.id,key))
    with pytest.raises(NotFound):run(checklist.add_personal_item(P,'intern-ivan','delivery.git'))
    with pytest.raises(NotFound):run(checklist.add_personal_item(P,'missing','platform.git'))


def test_common_and_done_cannot_be_removed(store,snapshot):
    before=snapshot()
    with pytest.raises(Forbidden):run(checklist.remove_personal_item(P,'anya.w1.meet-team'))
    assert snapshot()==before
    run(checklist.set_item_status(A,'anya.p.git','done'))
    with pytest.raises(Conflict):run(checklist.remove_personal_item(P,'anya.p.git'))
    assert snapshot().items['anya.p.git'].status=='done'


def test_unrelated_skill_change_does_not_undo_mentor_personalization(store,snapshot):
    run(checklist.add_personal_item(P,A.id,'platform.sql'))
    run(checklist.remove_personal_item(P,'anya.p.git'))
    run(hiring.set_skill_level(P,A.id,'ci','familiar'))
    assert 'anya.p.sql' in snapshot().items
    assert 'anya.p.git' not in snapshot().items
    # Изменение именно SQL пересобирает эту тему; ручной пункт не бессрочный.
    run(hiring.set_skill_level(P,A.id,'sql','familiar'))
    assert 'anya.p.sql' not in snapshot().items


def test_concurrent_additions_create_one_item_and_notification(store,snapshot):
    async def exercise():
        results=await asyncio.gather(*(checklist.add_personal_item(P,A.id,'platform.testing') for _ in range(2)),return_exceptions=True)
        assert sum(isinstance(r,Conflict) for r in results)==1
    run(exercise())
    assert len([i for i in snapshot().items.values() if i.intern_id==A.id and i.catalog_key=='platform.testing'])==1
    assert len([r for r in snapshot().reminders.values() if r.kind=='personal_item_added'])==1


def test_edit_persists_across_store_restart(onboarding_dsn,monkeypatch):
    from app.mcp_server import storage
    from app.mcp_server.postgres import PostgresStore
    from app.mcp_server.seed import load_seed
    first=PostgresStore(onboarding_dsn);monkeypatch.setattr(storage,'get_store',lambda:first)
    run(first.initialize(load_seed(),reset=True))
    run(checklist.add_personal_item(P,A.id,'platform.sql'))
    run(checklist.remove_personal_item(P,'anya.p.git'))
    run(first.close())
    second=PostgresStore(onboarding_dsn);monkeypatch.setattr(storage,'get_store',lambda:second)
    try:
        plan=run(checklist.get_plan(P,A.id))
        assert 'anya.p.git' not in {i.id for i in plan.items}
        assert next(i for i in plan.items if i.id=='anya.p.sql').reason=='добавил наставник'
    finally:run(second.close())
