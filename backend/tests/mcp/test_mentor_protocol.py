"""MCP может готовить, но не подтверждать действия вместо человека."""
import pytest
pytest.importorskip('mcp')
from mcp.shared.memory import create_connected_server_and_client_session as connected
from app import async_runner
from app.mcp_server import mentor_inbox as inbox, server
from .test_protocol import data, text
run = async_runner.run

def test_bonus_catalog_and_confirmation_boundary(store):
    async def exercise():
        async with connected(server.create_server('intern-anya')) as client:
            tools = {t.name: t for t in (await client.list_tools()).tools if t.name.startswith('mentor_')}
            assert set(tools) == {'mentor_draft_question', 'mentor_get_question', 'mentor_list_questions',
                                  'mentor_draft_answer', 'mentor_draft_publication', 'mentor_get_draft'}
            for name, tool in tools.items():
                assert 'user_id' not in tool.inputSchema['properties']
                if 'draft_' in name:
                    assert tool.annotations.idempotentHint is False
            draft = data(await client.call_tool('mentor_draft_question', {'text': 'Демо-вопрос'}))
            assert data(await client.call_tool('mentor_get_draft', {'draft_id': draft['id']})) == draft
            for name in ('confirm_question', 'mentor_confirm_question', 'confirm_answer', 'retry_publication'):
                assert (await client.call_tool(name, {'draft_id': draft['id']})).isError
            assert len(data(await client.call_tool('mentor_list_questions', {}))['result']) == 1
            q = await inbox.confirm_question('intern-anya', draft['id'])  # клик в доверенном UI
            assert data(await client.call_tool('mentor_get_question', {'question_id': q.id}))['status'] == 'pending'
            foreign = await client.call_tool('mentor_get_question', {'question_id': 'MQ-demo-delivery'})
            missing = await client.call_tool('mentor_get_question', {'question_id': 'missing'})
            assert foreign.isError and foreign == missing and 'Не найдено' in text(foreign)
        async with connected(server.create_server('mentor-petr')) as client:
            draft = data(await client.call_tool('mentor_draft_answer', {'question_id': q.id, 'text': 'Ответ'}))
            await inbox.confirm_answer('mentor-petr', draft['id'])
            publication = data(await client.call_tool('mentor_draft_publication', {'question_id': q.id}))
            assert publication['status'] == 'pending'
            denied = await client.call_tool('mentor_get_draft', {'draft_id': publication['id'], 'user_id':'intern-anya'})
            assert data(denied)['owner_id'] == 'mentor-petr'  # аргумент не меняет привязку процесса
    run(exercise())

def test_stdio_owner_also_closes_publication_store(store, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app import rag
    publication = SimpleNamespace(store=SimpleNamespace(close=AsyncMock()))
    instance = server.create_server('intern-anya')
    monkeypatch.setattr(instance, 'run_stdio_async', AsyncMock())
    monkeypatch.setattr(server, 'create_server', lambda user_id: instance)
    monkeypatch.setattr(rag, 'get_service', lambda: publication)
    server.main(['--user', 'intern-anya'])
    publication.store.close.assert_awaited_once()
