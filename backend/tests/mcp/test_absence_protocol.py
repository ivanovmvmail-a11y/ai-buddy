"""Протокол MCP: подготовка, чтение, отдельная роль лидера и скрытая причина."""
import pytest
pytest.importorskip('mcp')
from mcp.shared.memory import create_connected_server_and_client_session as connected
from app import async_runner
from app.mcp_server import absence, server
from .test_protocol import data, text
run = async_runner.run

def test_absence_protocol_and_no_confirmation_tools(store):
    async def exercise():
        async with connected(server.create_server('intern-anya')) as client:
            tools = {t.name:t for t in (await client.list_tools()).tools if t.name.startswith('absence_')}
            assert set(tools) == {'absence_draft_request','absence_get_request','absence_list_requests',
                                  'absence_draft_decision','absence_list_facts','absence_get_draft'}
            for name, tool in tools.items():
                assert 'user_id' not in tool.inputSchema['properties']
                if 'draft_' in name: assert tool.annotations.idempotentHint is False
            draft = data(await client.call_tool('absence_draft_request', {'day':'2026-11-12','reason':'personal'}))
            assert data(await client.call_tool('absence_get_draft', {'draft_id':draft['id']})) == draft
            assert len(data(await client.call_tool('absence_list_requests',{}))['result']) == 1
            for name in ('absence_confirm_absence','confirm_absence','absence_confirm_decision'):
                assert (await client.call_tool(name, {'draft_id':draft['id']})).isError
            request = await absence.confirm_absence('intern-anya', draft['id'])
            assert data(await client.call_tool('absence_get_request',{'request_id':request.id}))['status'] == 'pending'
            assert (await client.call_tool('absence_draft_decision', {'request_id':request.id,'approve':True,'user_id':'lead-olga'})).isError
            foreign = await client.call_tool('absence_get_request',{'request_id':'ABS-demo-delivery'})
            missing = await client.call_tool('absence_get_request',{'request_id':'missing'})
            assert foreign == missing and foreign.isError and 'Не найдено' in text(foreign)
        async with connected(server.create_server('lead-olga')) as lead:
            draft = data(await lead.call_tool('absence_draft_decision',{'request_id':request.id,'approve':True}))
            await absence.confirm_decision('lead-olga', draft['id'])
        async with connected(server.create_server('mentor-petr')) as mentor:
            facts = data(await mentor.call_tool('absence_list_facts',{'intern_id':'intern-anya'}))['result']
            assert any(f['day']=='2026-11-12' for f in facts)
            assert all(set(f)=={'intern_id','day'} for f in facts)
            assert (await mentor.call_tool('absence_get_request',{'request_id':request.id})).isError
    run(exercise())
