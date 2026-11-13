import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import clock, checklist, hiring
from app.mcp_server.errors import NotFound
from .test_skill_suggestions import A,P,suggestions

run=async_runner.run

def own(user):
    return run(clock.list_reminders(user))


def test_skill_change_rebuild_emits_one_fact_and_no_personal_notice(store,snapshot):
    run(hiring.set_skill_level(P,A.id,'testing','novice'))
    notifications=own(A)
    assert len(notifications)==1 and notifications[0].kind=='skill_changed'
    assert notifications[0].action.topic=='testing' and 'новичок' not in notifications[0].text
    assert snapshot().items['anya.p.testing'].kind=='personal'
    run(hiring.set_skill_level(P,A.id,'testing','novice'))
    assert own(A)==notifications
    run(hiring.set_skill_level(P,A.id,'testing','familiar'))
    assert next(r for r in own(A) if r.id==notifications[0].id).status=='done'
    assert len([r for r in own(A) if r.status=='active'])==1
    assert not any(r.kind=='personal_item_added' for r in own(A))
    assert 'anya.p.testing' not in snapshot().items


def test_suggestion_is_mentor_only_rejection_does_not_notify_intern(store):
    run(hiring.mark_known(A,'anya.p.git'))
    s=suggestions()[0]
    mentor=next(r for r in own(P) if r.kind=='skill_suggestion')
    assert mentor.suggestion_id==s.id and mentor.action.target=='skill_suggestion'
    assert mentor.action.label=='Решить'
    assert own(A)==[]
    for user in DEMO_USERS.values():
        if user.id==P.id:continue
        assert mentor.id not in {r.id for r in own(user)}
        with pytest.raises(NotFound):run(clock.done_reminder(user,mentor.id))
    run(hiring.mark_known(A,'anya.w1.notes'))
    assert len([r for r in own(P) if r.kind=='skill_suggestion'])==1
    run(hiring.decide_suggestion(P,s.id,False))
    assert next(r for r in own(P) if r.id==mentor.id).status=='done'
    assert own(A)==[]


def test_accept_notifies_result_and_snooze_reactivates_on_related_intern_day(store):
    run(hiring.mark_known(A,'anya.p.git'))
    s=suggestions()[0]
    reminder=next(r for r in own(P) if r.kind=='skill_suggestion')
    snoozed=run(clock.snooze_reminder(P,reminder.id,2))
    assert snoozed.snooze_until_day==4
    run(clock.advance_day(A,A.id))
    assert next(r for r in own(P) if r.id==reminder.id).status=='snoozed'
    run(clock.advance_day(A,A.id))
    assert next(r for r in own(P) if r.id==reminder.id).status=='active'
    run(hiring.decide_suggestion(P,s.id,True))
    changed=[r for r in own(A) if r.kind=='skill_changed']
    assert len(changed)==1 and 'Git — знаком' in changed[0].text
    assert 'предлагает' not in changed[0].text
    assert next(r for r in own(P) if r.id==reminder.id).status=='done'


def test_old_model_kind_is_inferred_without_breaking_old_fields():
    from app.mcp_server.models import Reminder
    base={'id':'old','user_id':A.id,'text':'demo','created_day':1}
    assert Reminder(**base,request_id='request').kind=='access_request'
    assert Reminder(**base,plan_item_id='item').kind=='plan_item'


def test_mcp_reminders_include_only_active_own_result_and_private_proposal(store):
    pytest.importorskip('mcp')
    from mcp.shared.memory import create_connected_server_and_client_session as connected
    from app.mcp_server.server import create_server
    from .test_protocol import data
    async def exercise():
        await hiring.mark_known(A,'anya.p.git')
        s=(await hiring.list_suggestions(P))[0]
        async with connected(create_server(A.id)) as intern:
            assert data(await intern.call_tool('list_reminders',{}))['result']==[]
            assert (await intern.call_tool('decide_suggestion',{'suggestion_id':s.id,'accept':True})).isError
        async with connected(create_server(P.id)) as mentor:
            rows=data(await mentor.call_tool('list_reminders',{}))['result']
            assert len(rows)==1 and rows[0]['kind']=='skill_suggestion'
            await clock.snooze_reminder(P,rows[0]['id'])
            assert data(await mentor.call_tool('list_reminders',{}))['result']==[]
        await hiring.decide_suggestion(P,s.id,True)
        async with connected(create_server(A.id)) as intern:
            rows=data(await intern.call_tool('list_reminders',{}))['result']
            assert len(rows)==1 and rows[0]['kind']=='skill_changed'
            assert rows[0]['action']['target']=='plan'
    run(exercise())
