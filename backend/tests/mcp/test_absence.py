"""Отгул: подтверждение, права всех восьми пользователей, приватная причина."""
import asyncio
from datetime import date, timedelta
import pytest
from pydantic import ValidationError
from app import async_runner
from app.agent.users import DEMO_USERS, Role
from app.mcp_server import absence, clock, drafts, storage
from app.mcp_server.errors import Conflict, NotFound
from app.mcp_server.postgres import PostgresStore
run = async_runner.run
ANYA, OLGA, PETR = 'intern-anya', 'lead-olga', 'mentor-petr'
DAY = date(2026, 11, 12)

def send(user=ANYA, day=DAY, reason='personal'):
    return run(absence.confirm_absence(user, run(absence.draft_absence(user, day, reason)).id))

def decide(request, approve=True, user=OLGA):
    return run(absence.confirm_decision(user, run(absence.draft_decision(user, request.id, approve)).id))

def test_no_delivery_before_confirm_owner_drafts_and_idempotency(store, snapshot):
    before = snapshot()
    draft = run(absence.draft_absence(ANYA, DAY, 'family'))
    assert snapshot().absence_requests == before.absence_requests and snapshot().events == before.events
    draft.payload['reason'] = 'study'
    assert run(drafts.get_draft(ANYA, draft.id)).payload['reason'] == 'family'
    for user in DEMO_USERS:
        if user == ANYA: continue
        for operation in (absence.confirm_absence, drafts.get_draft, drafts.cancel_draft):
            with pytest.raises(NotFound): run(operation(user, draft.id))
    result = run(absence.confirm_absence(ANYA, draft.id))
    assert result.reason == 'family' and result.lead_id == OLGA
    assert run(absence.confirm_absence(ANYA, draft.id)) == result
    assert sum(e.type == 'absence_requested' for e in snapshot().events) == 1
    with pytest.raises(Conflict): run(drafts.cancel_draft(ANYA, draft.id))
    decision = run(absence.draft_decision(OLGA, result.id, True))
    assert run(absence.get_request(ANYA, result.id)).status == 'pending'
    assert result.day not in {f.day for f in run(absence.list_absence_facts(PETR, ANYA))}
    approved = run(absence.confirm_decision(OLGA, decision.id))
    assert approved.status == 'approved' and approved.decided_day == 2
    assert run(absence.confirm_decision(OLGA, decision.id)) == approved
    facts = run(absence.list_absence_facts(PETR, ANYA))
    assert any(f.day == DAY for f in facts)
    assert all(set(f.model_dump()) == {'intern_id', 'day'} for f in facts)
    assert all(set(e.payload) <= {'status', 'day'} for e in snapshot().events if e.type.startswith('absence_'))
    approved.reason = 'study'
    assert run(absence.get_request(ANYA, result.id)).reason == 'family'

@pytest.mark.parametrize('user', DEMO_USERS)
def test_all_roles_and_same_not_found_for_foreign_missing(store, user):
    q = send()
    if user in (ANYA, OLGA):
        assert run(absence.get_request(user, q.id)).id == q.id
        assert q.id in {r.id for r in run(absence.list_requests(user))}
    else:
        with pytest.raises(NotFound) as foreign: run(absence.get_request(user, q.id))
        with pytest.raises(NotFound) as missing: run(absence.get_request(user, 'missing'))
        assert str(foreign.value) == str(missing.value)
        if DEMO_USERS[user].role in (Role.INTERN, Role.LEAD):
            assert q.id not in {r.id for r in run(absence.list_requests(user))}
        else:
            with pytest.raises(NotFound): run(absence.list_requests(user))
    if user != OLGA:
        with pytest.raises(NotFound): run(absence.draft_decision(user, q.id, True))
    if user != PETR:
        with pytest.raises(NotFound): run(absence.list_absence_facts(user, ANYA))
    if not user.startswith('intern-'):
        with pytest.raises(NotFound): run(absence.draft_absence(user, DAY, 'personal'))
    with pytest.raises(NotFound): run(absence.get_request(user, 'missing'))


def test_other_team_can_use_own_lead_and_mentor(store):
    request = send('intern-ivan', reason='study')
    assert request.lead_id == 'lead-sergey'
    assert decide(request, user='lead-sergey').status == 'approved'
    assert DAY in {f.day for f in run(absence.list_absence_facts('mentor-maria', 'intern-ivan'))}
    with pytest.raises(NotFound): run(absence.list_absence_facts(PETR, 'intern-ivan'))
    with pytest.raises(NotFound): run(absence.list_absence_facts(PETR, 'missing'))
    with pytest.raises(NotFound): run(absence.draft_absence('unknown', DAY, 'personal'))


def test_closed_reason_date_and_strict_decision_validation(store):
    for day, reason in ((DAY, 'Медицинские подробности'), (DAY, ''), ('not-date', 'family')):
        with pytest.raises(ValidationError): run(absence.draft_absence(ANYA, day, reason))
    with pytest.raises(Conflict): run(absence.draft_absence(ANYA, date(2026, 11, 9), 'personal'))
    request = send()
    for invalid in ('true', 1, None):
        with pytest.raises(ValidationError): run(absence.draft_decision(OLGA, request.id, invalid))


def test_rejection_allows_new_request_and_stale_decision_is_conflict(store):
    request = send()
    first = run(absence.draft_decision(OLGA, request.id, False))
    competing = run(absence.draft_decision(OLGA, request.id, True))
    assert run(absence.confirm_decision(OLGA, first.id)).status == 'rejected'
    assert DAY not in {f.day for f in run(absence.list_absence_facts(PETR, ANYA))}
    with pytest.raises(Conflict): run(absence.confirm_decision(OLGA, competing.id))
    with pytest.raises(Conflict): run(absence.draft_decision(OLGA, request.id, True))
    assert send().id != request.id
    with pytest.raises(Conflict): run(absence.draft_absence(ANYA, DAY, 'personal'))


def test_cancelled_wrong_action_missing_and_duplicate_confirm(store):
    draft = run(absence.draft_absence(ANYA, DAY, 'personal'))
    other = run(absence.draft_absence(ANYA, DAY, 'family'))
    run(absence.confirm_absence(ANYA, draft.id))
    with pytest.raises(Conflict): run(absence.confirm_absence(ANYA, other.id))
    with pytest.raises(NotFound): run(absence.confirm_decision(ANYA, draft.id))
    for operation, user in ((absence.confirm_absence, ANYA), (absence.confirm_decision, OLGA), (drafts.get_draft, ANYA), (drafts.cancel_draft, ANYA)):
        with pytest.raises(NotFound): run(operation(user, 'missing'))
    cancelled = run(absence.draft_absence(ANYA, DAY + timedelta(days=1), 'study'))
    run(drafts.cancel_draft(ANYA, cancelled.id))
    with pytest.raises(Conflict): run(absence.confirm_absence(ANYA, cancelled.id))
    request = run(absence.confirm_absence(ANYA, draft.id))
    decision = run(absence.draft_decision(OLGA, request.id, True))
    run(drafts.cancel_draft(OLGA, decision.id))
    with pytest.raises(Conflict): run(absence.confirm_decision(OLGA, decision.id))
    with pytest.raises(NotFound): run(absence.confirm_decision(ANYA, decision.id))


def test_recheck_day_and_lead_and_team_at_confirmation(store, monkeypatch):
    draft = run(absence.draft_absence(ANYA, DAY, 'personal'))
    canonical = DEMO_USERS[ANYA]
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical.model_copy(update={'lead_id':None}))
    with pytest.raises(Conflict): run(absence.draft_absence(ANYA, DAY, 'personal'))
    # Меняется назначенный руководитель, но остаётся внутри той же команды.
    monkeypatch.setitem(DEMO_USERS, 'lead-new', DEMO_USERS[OLGA].model_copy(update={'id':'lead-new'}))
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical.model_copy(update={'lead_id':'lead-new'}))
    with pytest.raises(Conflict): run(absence.confirm_absence(ANYA, draft.id))
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical)
    run(clock.advance_day(DEMO_USERS[ANYA], ANYA)); run(clock.advance_day(DEMO_USERS[ANYA], ANYA))
    with pytest.raises(Conflict): run(absence.confirm_absence(ANYA, draft.id))
    request = send(day=DAY + timedelta(days=10))
    monkeypatch.setitem(DEMO_USERS, ANYA, canonical.model_copy(update={'team':'changed'}))
    assert not run(absence.list_requests(ANYA))
    with pytest.raises(NotFound): run(absence.get_request(ANYA, request.id))


def test_concurrent_confirmation_creates_one_request(store):
    draft = run(absence.draft_absence(ANYA, DAY, 'personal'))
    async def exercise(): return await asyncio.gather(*(absence.confirm_absence(ANYA, draft.id) for _ in range(2)))
    first, second = run(exercise())
    assert first == second


def test_postgres_restart_and_reset(store, monkeypatch):
    request = decide(send())
    if not isinstance(store, PostgresStore):
        assert run(absence.get_request(ANYA, request.id)) == request
        return
    run(store.close())
    reopened = PostgresStore(store.database_url)
    monkeypatch.setattr(storage, 'get_store', lambda: reopened)
    try:
        assert run(absence.get_request(ANYA, request.id)) == request
        run(clock.reset_demo(DEMO_USERS[ANYA]))
        with pytest.raises(NotFound): run(absence.get_request(ANYA, request.id))
    finally: run(reopened.close())

def test_rls_hides_both_draft_and_request_even_with_select_grant(store):
    import psycopg
    from psycopg import sql
    from uuid import uuid4
    request = send()
    if not isinstance(store, PostgresStore):
        assert request.reason == 'personal'
        return
    reader = f'absence_reader_{uuid4().hex[:10]}'
    with psycopg.connect(store.database_url, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE ROLE {}').format(sql.Identifier(reader)))
        try:
            connection.execute(sql.SQL('GRANT SELECT ON service_drafts,absence_requests TO {}').format(sql.Identifier(reader)))
            with connection.transaction():
                connection.execute(sql.SQL('SET LOCAL ROLE {}').format(sql.Identifier(reader)))
                for table in ('service_drafts','absence_requests'):
                    assert connection.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone() == (0,)
        finally:
            connection.execute(sql.SQL('DROP OWNED BY {}').format(sql.Identifier(reader)))
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(reader)))
