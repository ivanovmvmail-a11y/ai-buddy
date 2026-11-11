"""S4: метка auto разрешает автовыдачу только read, повышенные права согласует человек."""
import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access
from app.mcp_server.errors import Conflict, Forbidden, NotFound
run=async_runner.run

@pytest.mark.parametrize('user_id',['intern-anya','intern-ivan'])
@pytest.mark.parametrize('resource_id',['jira','confluence'])
@pytest.mark.parametrize('level',['read','edit','admin'])
def test_auto_resource_requires_mentor_for_every_elevated_level(store,edit,snapshot,user_id,resource_id,level):
    actor=DEMO_USERS[user_id]
    edit(lambda data: setattr(data,'requests',{key:r for key,r in data.requests.items()
         if (r.intern_id,r.resource_id)!=(user_id,resource_id)}))
    before=snapshot()
    request=run(access.create_request(actor,resource_id,level,'Синтетическая задача'))
    new_events=snapshot().events[len(before.events):]
    if level=='read':
        assert request.status=='granted' and request.approver_id is None
        assert any(e.type=='access_request_decided' and e.user_id=='system' for e in new_events)
        return
    assert request.status=='pending_approval' and request.approver_id==actor.mentor_id
    assert not any(e.type=='access_request_decided' for e in new_events)
    if request.plan_item_id:
        item=snapshot().items[request.plan_item_id]
        assert item.status=='waiting' and item.waiting_for==actor.mentor_id
    for other in DEMO_USERS.values():
        if other.id==actor.mentor_id: continue
        with pytest.raises((Forbidden,NotFound)):
            run(access.decide_request(other,request.id,True))
    assert next(r for r in run(access.list_requests(actor)) if r.id==request.id).status=='pending_approval'
    assert run(access.decide_request(DEMO_USERS[actor.mentor_id],request.id,True)).status=='granted'

@pytest.mark.parametrize('mentor_id',[None,'missing','lead-olga'])
@pytest.mark.parametrize('level',['edit','admin'])
def test_elevated_auto_request_without_valid_mentor_is_atomic_conflict(store,monkeypatch,snapshot,mentor_id,level):
    actor=DEMO_USERS['intern-anya'].model_copy(update={'mentor_id':mentor_id})
    monkeypatch.setitem(DEMO_USERS,actor.id,actor)
    before=snapshot()
    with pytest.raises(Conflict,match='наставник'):
        run(access.create_request(actor,'jira',level,'Синтетическая задача'))
    assert snapshot()==before
    # read остаётся автоматическим, даже если наставник ещё не назначен.
    assert run(access.create_request(actor,'jira','read','Синтетическая задача')).status=='granted'

def test_resource_kind_does_not_bypass_level_check(store,edit):
    edit(lambda data:setattr(data.resources['bitbucket-platform'],'approver','auto'))
    request=run(access.create_request(DEMO_USERS['intern-anya'],'bitbucket-platform','admin','Синтетическая задача'))
    assert request.status=='pending_approval' and request.approver_id=='mentor-petr'
