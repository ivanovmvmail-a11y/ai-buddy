"""Официальный MCP клиент: ключ не раскрывается до подтверждения, результаты только владельцу."""
import pytest
pytest.importorskip('mcp')
from mcp.shared.memory import create_connected_server_and_client_session as connected
from app import async_runner
from app.mcp_server import self_check as check, server
from .test_protocol import data,text
run=async_runner.run

def test_self_check_protocol_private_results_no_confirmation_tool(store):
    async def exercise():
        async with connected(server.create_server('intern-anya')) as client:
            tools={t.name:t for t in (await client.list_tools()).tools if t.name.startswith('self_check_')}
            assert set(tools)=={'self_check_questions','self_check_draft_answers','self_check_get_result',
                                'self_check_list_results','self_check_get_draft'}
            assert all('user_id' not in t.inputSchema['properties'] for t in tools.values())
            assert tools['self_check_draft_answers'].annotations.idempotentHint is False
            questions=data(await client.call_tool('self_check_questions',{'topic':'git'}))['result']
            assert len(questions)==2 and all('correct_index' not in q and 'explanation' not in q for q in questions)
            assert not data(await client.call_tool('self_check_list_results',{}))['result']
            answers={q['id']:0 for q in questions}
            for invalid in (True,'0'):
                assert (await client.call_tool('self_check_draft_answers',{'topic':'git','answers':dict.fromkeys(answers,invalid)})).isError
            draft=data(await client.call_tool('self_check_draft_answers',{'topic':'git','answers':answers}))
            assert data(await client.call_tool('self_check_get_draft',{'draft_id':draft['id']}))==draft
            for name in ('confirm_answers','self_check_confirm_answers'):
                assert (await client.call_tool(name,{'draft_id':draft['id']})).isError
            result=await check.confirm_answers('intern-anya',draft['id'])
            review=data(await client.call_tool('self_check_get_result',{'result_id':result.id}))
            assert review['review'][0]['explanation'] and review['review'][0]['source_url']
        for user in ('intern-ivan','mentor-petr','lead-olga','hrbp-elena','curator-dmitry'):
            async with connected(server.create_server(user)) as other:
                foreign=await other.call_tool('self_check_get_result',{'result_id':result.id,'user_id':'intern-anya'})
                missing=await other.call_tool('self_check_get_result',{'result_id':'missing'})
                assert foreign==missing and foreign.isError and 'Не найдено' in text(foreign)
    run(exercise())
