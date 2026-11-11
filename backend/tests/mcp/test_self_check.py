"""Личная самопроверка: синтетические источники, все роли, отсутствие рейтинга/изменения навыков."""
import asyncio
import json
from pathlib import Path
import pytest
from pydantic import ValidationError
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import clock, drafts, self_check as check, storage
from app.mcp_server.errors import Conflict, NotFound
from app.mcp_server.postgres import PostgresStore
from app.rag.ingest import DEMO_DOCS, read_document
run = async_runner.run
ANYA = 'intern-anya'

@pytest.fixture(autouse=True)
def reset_bank_cache():
    clear = check._bank.cache_clear
    clear()
    yield
    clear()


def prepare(user=ANYA, topic='git'):
    questions = run(check.get_questions(user, topic))
    return run(check.draft_answers(user, topic, {q.id:0 for q in questions}))


def complete(user=ANYA, topic='git'):
    return run(check.confirm_answers(user, prepare(user, topic).id))

@pytest.mark.parametrize('user', ['intern-anya','intern-ivan'])
@pytest.mark.parametrize('topic', ['git','sql','ci'])
def test_two_questions_for_each_team_topic_private_review_with_sources(store, snapshot, user, topic):
    before = snapshot()
    questions = run(check.get_questions(user, topic))
    assert 2 <= len(questions) <= 3
    for q in questions:
        assert {'correct_index','explanation','team'}.isdisjoint(q.model_dump())
        assert q.topic == topic
        document = read_document(DEMO_DOCS / q.source_id.removeprefix('demo:'), q.source_id)
        assert document.team in (None, DEMO_USERS[user].team)
        assert q.source_url == check.SOURCE_BASE + q.source_id.removeprefix('demo:')
    questions[0].options[0] = 'tampered'
    assert run(check.get_questions(user, topic))[0].options[0] != 'tampered'
    draft = prepare(user, topic)
    assert snapshot().self_check_attempts == before.self_check_attempts and snapshot().events == before.events
    assert 'correct_index' not in str(draft.payload) and 'explanation' not in str(draft.payload)
    result = run(check.confirm_answers(user, draft.id))
    assert result.intern_id == user and result.topic == topic and len(result.review)==2
    assert run(check.confirm_answers(user, draft.id)) == result
    assert run(check.get_result(user, result.id)) == result
    assert run(check.list_results(user)) == [result]
    assert snapshot().profiles == before.profiles  # ни уровня, ни updated_at, ни skills_changed
    events = [e for e in snapshot().events[len(before.events):]]
    assert len(events)==1 and events[0].type=='self_check_completed' and events[0].payload == {'topic':topic}
    assert 'score' not in result.model_dump()
    for entry in result.review:
        assert entry.explanation and entry.source_url.startswith('https://')
    result.review[0].options[0]='tampered'
    assert run(check.get_result(user, result.id)).review[0].options[0]!='tampered'

@pytest.mark.parametrize('user', DEMO_USERS)
def test_all_eight_roles_private_results_and_unknown_same_as_foreign(store, user):
    result = complete()
    if user==ANYA:
        assert run(check.get_result(user, result.id)).id==result.id
    else:
        with pytest.raises(NotFound) as foreign: run(check.get_result(user, result.id))
        with pytest.raises(NotFound) as missing: run(check.get_result(user, 'missing'))
        assert str(foreign.value)==str(missing.value)
        if user=='intern-ivan':
            assert not run(check.list_results(user))
        else:
            with pytest.raises(NotFound): run(check.list_results(user))
            with pytest.raises(NotFound): run(check.get_questions(user,'git'))
            with pytest.raises(NotFound): run(check.draft_answers(user,'git',{}))
    with pytest.raises(NotFound): run(check.get_result(user,'missing'))


def test_draft_owner_cancel_wrong_action_and_unknown(store, edit):
    draft=prepare()
    returned=run(drafts.get_draft(ANYA,draft.id))
    returned.payload['answers'].clear()
    assert run(drafts.get_draft(ANYA,draft.id)).payload['answers']
    for user in DEMO_USERS:
        if user==ANYA: continue
        for operation in (check.confirm_answers,drafts.get_draft,drafts.cancel_draft):
            with pytest.raises(NotFound): run(operation(user,draft.id))
    run(drafts.cancel_draft(ANYA,draft.id))
    with pytest.raises(Conflict): run(check.confirm_answers(ANYA,draft.id))
    for operation in (check.confirm_answers,drafts.get_draft,drafts.cancel_draft):
        with pytest.raises(NotFound): run(operation(ANYA,'missing'))
    with pytest.raises(NotFound): run(check.get_questions('unknown','git'))
    draft=prepare()
    edit(lambda data:setattr(data.drafts[draft.id],'action','other'))
    with pytest.raises(NotFound): run(check.confirm_answers(ANYA,draft.id))
    done=prepare();run(check.confirm_answers(ANYA,done.id))
    with pytest.raises(Conflict): run(drafts.cancel_draft(ANYA,done.id))


def test_validation_and_foreign_question_ids(store):
    own=run(check.get_questions(ANYA,'git'))
    other=run(check.get_questions('intern-ivan','git'))
    with pytest.raises(ValidationError): run(check.get_questions(ANYA,'not-topic'))
    with pytest.raises(ValidationError): run(check.draft_answers(ANYA,'git',{}))
    for invalid in (-1,True,'0'):
        with pytest.raises(ValidationError): run(check.draft_answers(ANYA,'git',{q.id:invalid for q in own}))
    with pytest.raises(Conflict): run(check.draft_answers(ANYA,'git',{q.id:999 for q in own}))
    for ids in ([q.id for q in other],['missing.1','missing.2']):
        with pytest.raises(NotFound): run(check.draft_answers(ANYA,'git',{id:0 for id in ids}))


def test_unavailable_bank_and_change_after_draft_are_safe(store, monkeypatch, snapshot):
    draft=prepare();questions=check._bank()
    changed=tuple(q.model_copy(update={'explanation':'Новое объяснение'}) for q in questions)
    monkeypatch.setattr(check,'_bank',lambda:changed)
    with pytest.raises(Conflict): run(check.confirm_answers(ANYA,draft.id))
    assert not snapshot().self_check_attempts
    monkeypatch.setattr(check,'_bank',lambda:())
    with pytest.raises(Conflict): run(check.get_questions(ANYA,'sql'))


@pytest.mark.parametrize('case',['duplicate','source-missing','source-foreign','source-url','index'])
def test_bank_integrity_fails_closed(tmp_path,monkeypatch,case):
    source=json.loads(check.BANK_PATH.read_text())
    if case=='duplicate': source['questions'].append(source['questions'][0])
    if case=='source-missing': source['questions'][0]['source_id']='demo:missing.md'
    if case=='source-foreign': source['questions'][0]['source_id']='demo:08-delivery-sandbox.md'
    if case=='source-url': source['questions'][0]['source_url']='https://unrelated.invalid'
    if case=='index': source['questions'][0]['correct_index']=99
    path=tmp_path/'bank.json';path.write_text(json.dumps(source))
    monkeypatch.setattr(check,'BANK_PATH',path)
    with pytest.raises(ValueError): check._bank()


def test_no_data_reveal_after_team_change(store,monkeypatch):
    result=complete()
    user=DEMO_USERS[ANYA]
    monkeypatch.setitem(DEMO_USERS,ANYA,user.model_copy(update={'team':'changed'}))
    assert not run(check.list_results(ANYA))
    with pytest.raises(NotFound): run(check.get_result(ANYA,result.id))


def test_concurrent_confirm_and_persistence_reset(store,monkeypatch):
    draft=prepare()
    async def exercise(): return await asyncio.gather(check.confirm_answers(ANYA,draft.id),check.confirm_answers(ANYA,draft.id))
    first,second=run(exercise());assert first==second
    if not isinstance(store,PostgresStore): return
    run(store.close())
    reopened=PostgresStore(store.database_url)
    monkeypatch.setattr(storage,'get_store',lambda:reopened)
    try:
        assert run(check.get_result(ANYA,first.id))==first
        run(clock.reset_demo(DEMO_USERS[ANYA]))
        with pytest.raises(NotFound): run(check.get_result(ANYA,first.id))
    finally: run(reopened.close())


def test_rls_hides_result_and_draft_even_with_select_grant(store):
    import psycopg
    from psycopg import sql
    from uuid import uuid4
    complete()
    if not isinstance(store,PostgresStore): return
    reader=f'self_check_reader_{uuid4().hex[:10]}'
    with psycopg.connect(store.database_url,autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(reader)))
        try:
            connection.execute(sql.SQL('GRANT SELECT ON service_drafts,self_check_attempts TO {}').format(sql.Identifier(reader)))
            with connection.transaction():
                connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(reader)))
                for table in ('service_drafts','self_check_attempts'):
                    assert connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()==(0,)
        finally:
            connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(reader)))
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(reader)))
