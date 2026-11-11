"""S4: подтверждение черновика стажёром не заменяет согласование повышенных прав."""
import pytest
from .conftest import as_user

@pytest.mark.parametrize('level',['edit','admin'])
def test_confirmed_auto_resource_still_needs_own_mentor(client,level):
    intern=as_user('intern-anya')
    draft=client.post('/actions',headers=intern,json={'tool':'create_access_request',
        'params':{'resource_id':'jira','level':level,'justification':'Синтетическая задача'}})
    assert draft.status_code==201
    assert not client.get('/access/requests',headers=intern).json['requests']
    result=client.post(f"/actions/{draft.json['id']}/confirm",headers=intern)
    assert result.status_code==200 and result.json['status']=='done'
    request=result.json['result']['request']
    assert request['status']=='pending_approval' and request['approver_id']=='mentor-petr'
    url=f"/access/requests/{request['id']}/decide"
    assert client.post(url,headers=intern,json={'approve':True}).status_code==403
    assert client.post(url,headers=as_user('mentor-maria'),json={'approve':True}).status_code==404
    assert client.post(url,headers=as_user('mentor-petr'),json={'approve':True}).json['status']=='granted'
