import asyncio
import pytest
from pydantic import ValidationError
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist, hiring
from app.mcp_server.errors import Conflict, NotFound

run=async_runner.run
A=DEMO_USERS['intern-anya'];P=DEMO_USERS['mentor-petr']


def suggestions(status='pending'):
    return run(hiring.list_suggestions(P,A.id,status))


def test_two_closed_items_create_one_private_proposal_and_accept_rebuilds(store,snapshot):
    original=snapshot().profiles[A.id]
    run(checklist.set_item_status(A,'anya.w1.notes','done'))
    assert suggestions()==[]
    run(checklist.set_item_status(A,'anya.p.git','done'))
    result=suggestions()
    assert len(result)==1
    s=result[0]
    assert s.from_level=='novice' and s.to_level=='familiar'
    assert s.intern_name==A.name and s.topic_title=='Git'
    assert '2' in s.basis and 'evidence' not in s.model_dump()
    assert snapshot().profiles[A.id]==original
    run(checklist.set_item_status(A,'anya.p.git','done'))
    assert len(suggestions())==1
    accepted=run(hiring.decide_suggestion(P,s.id,True))
    assert accepted.status=='accepted' and accepted.decided_day==2
    assert snapshot().profiles[A.id].skills['git']=='familiar'
    assert snapshot().items['anya.p.git'].status=='done'
    with pytest.raises(Conflict):run(hiring.decide_suggestion(P,s.id,True))
    events=[e for e in snapshot().events if e.type.startswith('skill_suggestion_')]
    assert [e.type for e in events]==['skill_suggestion_created','skill_suggestion_decided']
    assert all('basis' not in e.payload for e in events)


def test_mark_known_does_not_close_item_or_change_skill_and_reject_requires_new_evidence(store,snapshot):
    before=snapshot()
    item=run(hiring.mark_known(A,'anya.p.git'))
    assert item.known_marked and item.status==before.items[item.id].status
    s=suggestions()[0]
    run(hiring.decide_suggestion(P,s.id,False))
    assert snapshot().profiles[A.id]==before.profiles[A.id]
    run(hiring.mark_known(A,item.id,False))
    run(hiring.mark_known(A,item.id,True))
    assert suggestions()==[]
    run(hiring.mark_known(A,'anya.w1.notes'))
    assert len(suggestions())==1
    assert len(suggestions(None))==2
    assert run(hiring.list_suggestions(P))[0].id==suggestions()[0].id


@pytest.mark.parametrize('user_id',list(DEMO_USERS))
def test_all_roles_and_nonexistent_are_indistinguishable(store,user_id):
    run(hiring.mark_known(A,'anya.p.git'))
    s=suggestions()[0];user=DEMO_USERS[user_id]
    if user_id!=P.id:
        for id in [s.id,'missing']:
            with pytest.raises(NotFound,match='^Не найдено$'):run(hiring.decide_suggestion(user,id,True))
        if user.role.value!='mentor':
            with pytest.raises(NotFound):run(hiring.list_suggestions(user))
        else:
            assert run(hiring.list_suggestions(user))==[]
        with pytest.raises(NotFound):run(hiring.list_suggestions(user,A.id))
    if user_id!=A.id:
        for id in ['anya.p.git','missing']:
            with pytest.raises(NotFound):run(hiring.mark_known(user,id))


def test_validation_and_stale_proposal_do_not_downgrade_profile(store,snapshot):
    with pytest.raises(ValidationError):run(hiring.mark_known(A,'anya.w1.meet-team'))
    with pytest.raises(ValidationError):run(hiring.mark_known(A,'anya.p.git','yes'))
    run(hiring.mark_known(A,'anya.p.git'))
    s=suggestions()[0]
    with pytest.raises(ValidationError):run(hiring.decide_suggestion(P,s.id,'false'))
    with pytest.raises(ValidationError):run(hiring.list_suggestions(P,A.id,'invalid'))
    run(hiring.set_skill_level(P,A.id,'git','confident'))
    with pytest.raises(Conflict):run(hiring.decide_suggestion(P,s.id,True))
    assert snapshot().profiles[A.id].skills['git']=='confident'
    assert suggestions('dismissed')[0].id==s.id
    with pytest.raises(Conflict):run(hiring.decide_suggestion(P,s.id,False))
    assert suggestions()==[]


def test_concurrent_known_creates_one_pending_and_pending_absorbs_new_evidence(store):
    async def exercise():
        await asyncio.gather(*(hiring.mark_known(A,'anya.p.git') for _ in range(5)))
        await hiring.mark_known(A,'anya.w1.notes')
    run(exercise())
    assert len(suggestions())==1
    run(hiring.decide_suggestion(P,suggestions()[0].id,False))
    run(hiring.mark_known(A,'anya.w1.notes',False))
    run(hiring.mark_known(A,'anya.w1.notes',True))
    assert suggestions()==[]


def test_new_closure_after_dismissal_can_propose_again(store,edit):
    run(checklist.set_item_status(A,'anya.w1.notes','done'))
    run(checklist.set_item_status(A,'anya.p.git','done'))
    run(hiring.decide_suggestion(P,suggestions()[0].id,False))
    run(checklist.set_item_status(P,'anya.p.git','in_progress','ещё практика'))
    run(checklist.set_item_status(A,'anya.p.git','done'))
    assert suggestions()==[]
    def add(data):
        item=data.items['anya.p.git'].model_copy(update={'id':'anya.extra.git','status':'not_started','catalog_key':None},deep=True)
        data.items[item.id]=item
    edit(add)
    run(checklist.set_item_status(A,'anya.extra.git','done'))
    assert len(suggestions())==1


def test_suggestion_and_private_evidence_persist_across_pool_restart(onboarding_dsn,monkeypatch):
    from app.mcp_server import storage
    from app.mcp_server.postgres import PostgresStore
    from app.mcp_server.seed import load_seed
    store=PostgresStore(onboarding_dsn)
    monkeypatch.setattr(storage,'get_store',lambda:store)
    run(store.initialize(load_seed(),reset=True))
    run(hiring.mark_known(A,'anya.p.git'))
    id=suggestions()[0].id
    run(hiring.decide_suggestion(P,id,False))
    run(store.close())
    second=PostgresStore(onboarding_dsn);monkeypatch.setattr(storage,'get_store',lambda:second)
    try:
        assert suggestions(None)[0].id==id
        run(hiring.mark_known(A,'anya.p.git',False));run(hiring.mark_known(A,'anya.p.git',True))
        assert suggestions()==[]
    finally:run(second.close())


def test_confident_topic_does_not_propose_and_missing_profile_is_not_found(store,edit):
    run(hiring.mark_known(A,'anya.w2.docs'))
    assert suggestions()==[]
    run(hiring.mark_known(A,'anya.p.git'))
    s=suggestions()[0]
    edit(lambda data:data.profiles.pop(A.id))
    with pytest.raises(NotFound):run(hiring.decide_suggestion(P,s.id,True))


@pytest.mark.parametrize('mentor_id',[None,'missing','lead-olga'])
def test_missing_or_invalid_mentor_does_not_create_automatic_assessment(store,monkeypatch,snapshot,mentor_id):
    user=A.model_copy(update={'mentor_id':mentor_id})
    monkeypatch.setitem(DEMO_USERS,A.id,user)
    run(hiring.mark_known(user,'anya.p.git'))
    assert snapshot().suggestions=={}
    assert snapshot().profiles[A.id].skills['git']=='novice'


def test_familiar_promotes_to_confident_only_after_mentor_and_filters_history(store,snapshot):
    run(hiring.set_skill_level(P,A.id,'git','familiar'))
    run(hiring.mark_known(A,'anya.w1.notes'))
    s=suggestions()[0]
    assert s.to_level=='confident'
    assert run(hiring.list_suggestions(P,status='dismissed'))==[]
    run(hiring.decide_suggestion(P,s.id,True))
    assert snapshot().profiles[A.id].skills['git']=='confident'
    assert run(hiring.list_suggestions(P,status='accepted'))[0].id==s.id
    with pytest.raises(NotFound):run(hiring.decide_suggestion(P,'missing',False))
    with pytest.raises(NotFound):run(hiring.mark_known(A,'anya.w1.channels'))
