"""Входящие: обе реализации, все роли, подтверждение, публикация и часы."""
from unittest.mock import AsyncMock
import pytest
from pydantic import ValidationError
from app import async_runner, rag
from app.agent.users import DEMO_USERS
from app.mcp_server import clock, drafts, mentor_inbox as inbox
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import Conflict, NotFound
from app.rag.embeddings import DeterministicEmbedder
from app.rag.service import RAGService
from app.rag.storage import InMemoryDocumentStore
run = async_runner.run
ANYA, PETR = 'intern-anya', 'mentor-petr'

def send(user=ANYA, text='Как проверить синтетическую миграцию?'):
    return run(inbox.confirm_question(user, run(inbox.draft_question(user, text)).id))

def answer(q, publish=False):
    return run(inbox.confirm_answer(PETR, run(inbox.draft_answer(PETR, q.id, 'Проверьте миграцию в учебной базе.', publish)).id))

def test_draft_requires_confirmation_and_owner(store, snapshot):
    before = snapshot()
    draft = run(inbox.draft_question(ANYA, '  Демо-вопрос  '))
    assert draft.payload['text'] == 'Демо-вопрос'
    assert snapshot().mentor_questions == before.mentor_questions and snapshot().events == before.events
    draft.payload['text'] = 'tampered'
    assert run(drafts.get_draft(ANYA, draft.id)).payload['text'] == 'Демо-вопрос'
    for user in DEMO_USERS:
        if user == ANYA: continue
        for operation in (drafts.get_draft, drafts.cancel_draft, inbox.confirm_question):
            with pytest.raises(NotFound): run(operation(user, draft.id))
    q = run(inbox.confirm_question(ANYA, draft.id))
    assert q.question == 'Демо-вопрос' and run(inbox.confirm_question(ANYA, draft.id)) == q
    assert sum(e.type == 'mentor_question_sent' for e in snapshot().events) == 1
    with pytest.raises(Conflict): run(drafts.cancel_draft(ANYA, draft.id))
    cancelled = run(inbox.draft_question(ANYA, 'Отмена'))
    assert run(drafts.cancel_draft(ANYA, cancelled.id)).status == 'cancelled'
    with pytest.raises(Conflict): run(inbox.confirm_question(ANYA, cancelled.id))
    for operation in (drafts.get_draft, drafts.cancel_draft, inbox.confirm_question):
        with pytest.raises(NotFound): run(operation(ANYA, 'missing'))
    with pytest.raises(NotFound): run(inbox.get_question('unknown', 'missing'))

@pytest.mark.parametrize('user', DEMO_USERS)
def test_acl_all_eight_and_non_disclosure(store, user):
    q = send()
    if user in (ANYA, PETR):
        assert run(inbox.get_question(user, q.id)).id == q.id
        assert q.id in {q.id for q in run(inbox.list_questions(user))}
    else:
        with pytest.raises(NotFound) as foreign: run(inbox.get_question(user, q.id))
        with pytest.raises(NotFound) as missing: run(inbox.get_question(user, 'absent'))
        assert str(foreign.value) == str(missing.value)
        if user in ('intern-ivan', 'mentor-maria'):
            assert q.id not in {q.id for q in run(inbox.list_questions(user))}
        else:
            with pytest.raises(NotFound): run(inbox.list_questions(user))
    if user != PETR:
        with pytest.raises(NotFound): run(inbox.draft_answer(user, q.id, 'Ответ'))
        with pytest.raises(NotFound): run(inbox.draft_publication(user, 'MQ-demo-platform'))
        with pytest.raises(NotFound): run(inbox.retry_publication(user, q.id))
    if not user.startswith('intern-'):
        with pytest.raises(NotFound): run(inbox.draft_question(user, 'Вопрос'))

def test_answer_publication_explicit_team_scoped(store, snapshot):
    q = send(text='PRIVATE_QUESTION')
    text = 'Аня, проверьте синтетическую миграцию. anya@example.test +7 (999) 123-45-67'
    draft = run(inbox.draft_answer(PETR, q.id, text, True))
    assert run(inbox.get_question(ANYA, q.id)).answer is None
    assert all(s not in draft.payload['public_content'] for s in ('Аня', 'anya@example.test', '999'))
    assert not run(rag.retrieve('миграцию', DEMO_USERS[ANYA]))
    result = run(inbox.confirm_answer(PETR, draft.id))
    assert result.publication_status == 'published' and result.answer == text
    assert run(inbox.confirm_answer(PETR, draft.id)) == result
    assert run(inbox.retry_publication(PETR, result.id)) == result
    assert run(inbox.get_question(ANYA, result.id)).answer == text
    hits = run(rag.retrieve('синтетическую миграцию', DEMO_USERS[ANYA]))
    assert hits and hits[0]['title'].startswith('Ответ наставника, ')
    assert 'PRIVATE_QUESTION' not in str(hits) and 'Аня' not in str(hits)
    assert not run(rag.retrieve('миграцию', DEMO_USERS['intern-ivan']))
    assert len(rag.get_memory_service().store.documents) == 1
    assert all(set(e.payload) <= {'status', 'kind', 'day'} for e in snapshot().events if e.type.startswith('mentor_'))
    with pytest.raises(Conflict): run(inbox.draft_answer(PETR, result.id, 'ещё'))
    with pytest.raises(Conflict): run(inbox.draft_publication(PETR, result.id))

def test_separate_publication_outbox_retry_competing_drafts(store, monkeypatch, caplog):
    q = send()
    first = run(inbox.draft_answer(PETR, q.id, 'Ответ без публикации'))
    stale = run(inbox.draft_answer(PETR, q.id, 'Другой ответ'))
    result = run(inbox.confirm_answer(PETR, first.id))
    assert result.publication_status == 'not_requested'
    with pytest.raises(Conflict): run(inbox.confirm_answer(PETR, stale.id))
    with pytest.raises(Conflict): run(inbox.retry_publication(PETR, result.id))
    with pytest.raises(Conflict): run(inbox.draft_publication(PETR, send().id))
    draft = run(inbox.draft_publication(PETR, result.id))
    competing = run(inbox.draft_publication(PETR, result.id))
    assert run(inbox.get_question(ANYA, result.id)).publication_status == 'not_requested'
    service = RAGService(DeterministicEmbedder(), InMemoryDocumentStore())
    original = service.ingest
    monkeypatch.setattr(service, 'ingest', AsyncMock(side_effect=RuntimeError('PRIVATE_DATABASE_SECRET')))
    monkeypatch.setattr(rag, 'get_service', lambda: service)
    pending = run(inbox.confirm_publication(PETR, draft.id))
    assert pending.answer and pending.publication_status == 'pending'
    assert 'RuntimeError' in caplog.text and 'PRIVATE_DATABASE_SECRET' not in caplog.text
    with pytest.raises(Conflict): run(inbox.confirm_publication(PETR, competing.id))
    monkeypatch.setattr(service, 'ingest', original)
    assert run(inbox.confirm_publication(PETR, draft.id)).publication_status == 'published'
    assert run(inbox.confirm_publication(PETR, draft.id)).publication_status == 'published'
    assert len(service.store.documents) == 1
    result.answer = 'tampered'
    assert run(inbox.get_question(ANYA, result.id)).answer == 'Ответ без публикации'

def test_answer_outbox_failure_and_cancelled_drafts(store, monkeypatch):
    q = send()
    draft = run(inbox.draft_answer(PETR, q.id, 'Сохранённый ответ', True))
    service = RAGService(DeterministicEmbedder(), InMemoryDocumentStore())
    monkeypatch.setattr(service, 'ingest', AsyncMock(side_effect=OSError()))
    monkeypatch.setattr(rag, 'get_service', lambda: service)
    assert run(inbox.confirm_answer(PETR, draft.id)).publication_status == 'pending'
    assert run(inbox.confirm_answer(PETR, draft.id)).answer == 'Сохранённый ответ'
    for prepare, confirm in ((lambda: inbox.draft_answer(PETR, send().id, 'Ответ'), inbox.confirm_answer),
                             (lambda: inbox.draft_publication(PETR, 'MQ-demo-platform'), inbox.confirm_publication)):
        draft = run(prepare())
        run(drafts.cancel_draft(PETR, draft.id))
        with pytest.raises(Conflict): run(confirm(PETR, draft.id))
        with pytest.raises(NotFound): run(confirm(ANYA, draft.id))

@pytest.mark.parametrize('text', ['', ' ', 'a' * 3001])
def test_question_validation(store, text):
    with pytest.raises(ValidationError): run(inbox.draft_question(ANYA, text))

def test_answer_validation_wrong_action(store):
    q = send()
    for text, publish in (('', False), ('a' * 6001, False), ('Ответ', 'true')):
        with pytest.raises(ValidationError): run(inbox.draft_answer(PETR, q.id, text, publish))
    draft = run(inbox.draft_question(ANYA, 'Вопрос'))
    with pytest.raises(NotFound): run(inbox.confirm_answer(ANYA, draft.id))

def test_assignment_and_team_rechecked(store, monkeypatch):
    draft = run(inbox.draft_question(ANYA, 'Вопрос'))
    canonical = DEMO_USERS[ANYA]
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical.model_copy(update={'mentor_id': 'mentor-maria'}))
    with pytest.raises(Conflict): run(inbox.confirm_question(ANYA, draft.id))
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical.model_copy(update={'mentor_id': None}))
    with pytest.raises(Conflict): run(inbox.draft_question(ANYA, 'Вопрос'))
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical)
    q = send()
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical.model_copy(update={'team': 'changed'}))
    assert not run(inbox.list_questions(ANYA))
    with pytest.raises(NotFound): run(inbox.get_question(ANYA, q.id))

def test_reminder_threshold_once_snooze_complete(store, snapshot):
    q = send()
    assert not [r for r in run(clock.cron_tick(SYSTEM_ACTOR, q.created_day + 1)) if r.mentor_question_id]
    created = [r for r in run(clock.cron_tick(SYSTEM_ACTOR, q.created_day + 2)) if r.mentor_question_id]
    assert len(created) == 1 and created[0].user_id == PETR
    rem = created[0]
    assert not [r for r in run(clock.cron_tick(SYSTEM_ACTOR, q.created_day + 3)) if r.mentor_question_id]
    assert rem.id not in {r.id for r in run(clock.list_reminders(DEMO_USERS[ANYA]))}
    with pytest.raises(NotFound): run(clock.done_reminder(DEMO_USERS[ANYA], rem.id))
    snoozed = run(clock.snooze_reminder(DEMO_USERS[PETR], rem.id, 2))
    run(clock.cron_tick(SYSTEM_ACTOR, snoozed.snooze_until_day - 1))
    assert next(r for r in run(clock.list_reminders(DEMO_USERS[PETR], include_mentor=True)) if r.id == rem.id).status == 'snoozed'
    run(clock.cron_tick(SYSTEM_ACTOR, snoozed.snooze_until_day))
    assert next(r for r in run(clock.list_reminders(DEMO_USERS[PETR], include_mentor=True)) if r.id == rem.id).status == 'active'
    answer(q)
    assert next(r for r in run(clock.list_reminders(DEMO_USERS[PETR], include_mentor=True)) if r.id == rem.id).status == 'done'
    assert all('intern_id' not in e.payload for e in snapshot().events if e.type.startswith('mentor_'))
    other = send('intern-ivan')
    run(clock.advance_day(DEMO_USERS[ANYA], ANYA))
    assert not [r for r in snapshot().reminders.values() if r.mentor_question_id == other.id]

def test_persistence_and_postgres_rag(store, monkeypatch):
    from app.mcp_server.postgres import PostgresStore
    if not isinstance(store, PostgresStore):
        assert run(inbox.get_question(ANYA, answer(send()).id)).answer
        return
    import psycopg
    from pathlib import Path
    from app.rag.postgres import PostgresDocumentStore
    migration = next((Path(__file__).resolve().parents[3] / 'supabase/migrations').glob('*_rag_documents.sql'))
    with psycopg.connect(store.database_url, autocommit=True) as connection:
        if connection.execute("SELECT to_regclass('public.rag_documents')").fetchone()[0] is None:
            connection.execute(migration.read_text())
    service = RAGService(DeterministicEmbedder(), PostgresDocumentStore(store.database_url))
    monkeypatch.setattr(rag, 'get_service', lambda: service)
    q = answer(send(), publish=True)
    run(store.close())
    from app.mcp_server import storage
    reopened = PostgresStore(store.database_url)
    monkeypatch.setattr(storage, 'get_store', lambda: reopened)
    try:
        assert run(inbox.get_question(ANYA, q.id)).publication_status == 'published'
        assert run(rag.retrieve('миграцию', DEMO_USERS[ANYA]))
        assert not run(rag.retrieve('миграцию', DEMO_USERS['intern-ivan']))
    finally:
        run(reopened.close()); run(service.store.close())

def test_advance_drives_question_reminder_and_manual_completion(store, snapshot):
    q = send()
    run(clock.advance_day(DEMO_USERS[ANYA], ANYA))
    run(clock.advance_day(DEMO_USERS[ANYA], ANYA))
    reminder = next(r for r in snapshot().reminders.values() if r.mentor_question_id == q.id)
    assert run(clock.done_reminder(DEMO_USERS[PETR], reminder.id)).status == 'done'
    run(clock.cron_tick(SYSTEM_ACTOR, 100))
    assert next(r for r in snapshot().reminders.values() if r.id == reminder.id).status == 'done'
    # Ответ без активного напоминания остаётся идемпотентным.
    assert answer(q).status == 'answered'

def test_concurrent_approved_publication_is_idempotent(store, monkeypatch, snapshot):
    import asyncio
    q = answer(send())
    draft = run(inbox.draft_publication(PETR, q.id))
    service = RAGService(DeterministicEmbedder(), InMemoryDocumentStore())
    original = service.ingest
    async def exercise():
        arrived = 0
        ready = asyncio.Event()
        async def ingest(document):
            nonlocal arrived
            arrived += 1
            if arrived == 2: ready.set()
            await ready.wait()
            return await original(document)
        monkeypatch.setattr(service, 'ingest', ingest)
        monkeypatch.setattr(rag, 'get_service', lambda: service)
        values = await asyncio.gather(inbox.confirm_publication(PETR, draft.id), inbox.confirm_publication(PETR, draft.id))
        assert all(q.publication_status == 'published' for q in values)
    run(exercise())
    assert len(service.store.documents) == 1
    assert sum(e.type == 'mentor_answer_published' for e in snapshot().events) == 1
