"""Регрессии ревью #45: автодеплой, обезличивание, поиск, reset/race и старый HTTP контракт."""
from functools import cache
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app import async_runner, rag
from app.agent.users import DEMO_USERS
from app.mcp_server import clock, mentor_inbox as inbox
from app.mcp_server.errors import Conflict, NotFound
from app.mcp_server.postgres import PostgresStore
from app.rag.embeddings import DeterministicEmbedder
from app.rag.service import RAGService
from app.rag.storage import Document, InMemoryDocumentStore
from .test_mentor_inbox import send, answer
run=async_runner.run


def test_public_preview_redacts_inflections_and_yo_but_keeps_dates_and_numbers(store):
    q=send()
    text='Ане Смирновой, Петр и Петра, Ивану Кузнецову: 2026-11-20, 1 000 000 000, intern-anya; +7 (999) 123-45-67.'
    draft=run(inbox.draft_answer('mentor-petr',q.id,text,True))
    preview=draft.payload['public_content']
    assert all(name not in preview for name in ('Ане','Смирновой','Петр','Петра','Ивану','Кузнецову','intern-anya','999'))
    assert '2026-11-20' in preview and '1 000 000 000' in preview
    assert run(inbox.get_question('intern-anya',q.id)).answer is None
    assert run(inbox.confirm_answer('mentor-petr',draft.id)).public_content==preview


def test_local_answer_is_not_a_source_for_unrelated_query(store):
    answer(send(),True)
    assert run(rag.retrieve('миграцию',DEMO_USERS['intern-anya']))
    assert not run(rag.retrieve('Погода на Марсе завтра',DEMO_USERS['intern-anya']))


def test_reset_removes_only_published_answers(store):
    service=rag.get_memory_service()
    run(service.ingest(Document(source_id='regular',title='Демо-документ',content='Учебная миграция')))
    q=answer(send(),True)
    assert q.source_id in service.store.documents
    run(clock.reset_demo(DEMO_USERS['intern-anya']))
    assert q.source_id not in service.store.documents and 'regular' in service.store.documents
    with pytest.raises(NotFound): run(inbox.get_question('intern-anya',q.id))


def test_reset_during_ingest_does_not_delete_new_generation_or_leave_orphan(store,monkeypatch):
    service=rag.get_memory_service()
    original=service.ingest
    later=[]
    async def racing(document):
        await original(document)
        await clock.reset_demo(DEMO_USERS['intern-anya'])
        monkeypatch.setattr(service,'ingest',original)
        draft=await inbox.draft_publication('mentor-petr','MQ-demo-platform')
        later.append(await inbox.confirm_publication('mentor-petr',draft.id))
    monkeypatch.setattr(service,'ingest',racing)
    draft=run(inbox.draft_publication('mentor-petr','MQ-demo-platform'))
    with pytest.raises(NotFound): run(inbox.confirm_publication('mentor-petr',draft.id))
    current=run(inbox.get_question('mentor-petr','MQ-demo-platform'))
    assert current==later[0] and current.publication_status=='published'
    assert set(service.store.documents)=={current.source_id}


def test_reset_cleanup_failure_does_not_claim_success_or_forget_question(store,monkeypatch,snapshot):
    q=answer(send(),True)
    before=snapshot()
    monkeypatch.setattr(rag.get_memory_service().store,'delete',AsyncMock(side_effect=RuntimeError('PRIVATE_DATA')))
    with pytest.raises(Conflict) as error: run(clock.reset_demo(DEMO_USERS['intern-anya']))
    assert 'PRIVATE_DATA' not in str(error.value) and snapshot()==before
    assert run(inbox.get_question('intern-anya',q.id)).publication_status=='published'


def test_legacy_reminders_hide_bonus_until_ui_opt_in(store):
    q=send()
    from app.mcp_server._system import SYSTEM_ACTOR
    run(clock.cron_tick(SYSTEM_ACTOR,q.created_day+2))
    assert not any(r.mentor_question_id for r in run(clock.list_reminders(DEMO_USERS['mentor-petr'])))
    visible=run(clock.list_reminders(DEMO_USERS['mentor-petr'],include_mentor=True))
    assert any(r.mentor_question_id==q.id for r in visible)
    assert all('mentor_question_id' not in r.model_dump() for r in visible)


def test_cached_service_never_initializes_on_shutdown(monkeypatch):
    created=[]
    @cache
    def fake():
        created.append(True)
        return SimpleNamespace()
    monkeypatch.setattr(rag,'get_service',fake)
    assert rag.cached_service() is None and not created
    actual=fake()
    assert rag.cached_service() is actual and created==[True]


def test_delete_contract_for_both_document_stores(store):
    if isinstance(store,PostgresStore):
        import psycopg
        from .conftest import MIGRATION
        from app.rag.postgres import PostgresDocumentStore
        migration=next(MIGRATION.parent.glob('*_rag_documents.sql'))
        with psycopg.connect(store.database_url,autocommit=True) as connection:
            if connection.execute("SELECT to_regclass('public.rag_documents')").fetchone()[0] is None:
                connection.execute(migration.read_text())
        documents=PostgresDocumentStore(store.database_url)
    else: documents=InMemoryDocumentStore()
    service=RAGService(DeterministicEmbedder(),documents)
    try:
        for name in ('delete-me','keep-me'):
            run(service.ingest(Document(source_id=name,title=name,content=name,team='Тест удаления')))
        run(documents.delete('delete-me'));run(documents.delete('delete-me'))
        user=DEMO_USERS['intern-anya'].model_copy(update={'team':'Тест удаления'})
        titles={h['title'] for h in run(service.retrieve('проверка',user,100))}
        assert 'keep-me' in titles and 'delete-me' not in titles
    finally:
        run(documents.delete('keep-me'));run(documents.close())

def test_http_reminders_preserve_existing_response_contract(store):
    from app.main import create_app
    from app.mcp_server._system import SYSTEM_ACTOR
    q=send()
    run(clock.cron_tick(SYSTEM_ACTOR,q.created_day+2))
    response=create_app().test_client().get('/reminders',headers={'X-User-Id':'mentor-petr'})
    assert response.status_code==200
    assert all('mentor_question_id' not in r and 'входящих' not in r['text'] for r in response.json['reminders'])


def test_question_and_draft_rls_even_with_explicit_select(store):
    q=send()
    if not isinstance(store,PostgresStore):
        assert q.status=='pending'
        return
    import psycopg
    from psycopg import sql
    from uuid import uuid4
    reader=f'mentor_reader_{uuid4().hex[:10]}'
    with psycopg.connect(store.database_url,autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(reader)))
        try:
            connection.execute(sql.SQL('GRANT SELECT ON service_drafts,mentor_questions TO {}').format(sql.Identifier(reader)))
            with connection.transaction():
                connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(reader)))
                for table in ('service_drafts','mentor_questions'):
                    assert connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()==(0,)
        finally:
            connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(reader)))
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(reader)))
