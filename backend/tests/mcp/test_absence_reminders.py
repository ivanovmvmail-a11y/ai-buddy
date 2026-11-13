from datetime import date
import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import absence, clock
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server.errors import NotFound
from .test_absence import send, decide, ANYA, OLGA, PETR

run=async_runner.run

def reminders(user):
    return run(clock.list_reminders(DEMO_USERS[user]))


def test_waiting_new_decision_and_private_fact(store, snapshot):
    req=send(day=date(2026,11,15),reason='family')
    new=[r for r in reminders(OLGA) if r.kind=='absence_new']
    assert len(new)==1 and new[0].absence_request_id==req.id
    assert new[0].action.target=='absence_request'
    assert new[0].text == 'Новая заявка на отгул: Аня Смирнова, 15.11'
    assert not any(r.kind=='absence_pending' for r in reminders(ANYA))
    run(clock.advance_day(DEMO_USERS[ANYA],ANYA))
    assert not any(r.kind=='absence_pending' for r in reminders(ANYA))
    run(clock.advance_day(DEMO_USERS[ANYA],ANYA))
    waiting=[r for r in reminders(ANYA) if r.kind=='absence_pending']
    assert len(waiting)==1 and '2 дня' in waiting[0].text
    run(clock.cron_tick(SYSTEM_ACTOR))
    assert len([r for r in reminders(ANYA) if r.kind=='absence_pending'])==1
    run(clock.snooze_reminder(DEMO_USERS[ANYA],waiting[0].id))
    decide(req)
    assert next(r for r in reminders(ANYA) if r.id==waiting[0].id).status=='done'
    assert next(r for r in reminders(OLGA) if r.id==new[0].id).status=='done'
    decided=[r for r in reminders(ANYA) if r.kind=='absence_decided']
    assert len(decided)==1 and 'согласован' in decided[0].text
    fact=[r for r in reminders(PETR) if r.kind=='absence_fact']
    assert len(fact)==1 and '15.11' in fact[0].text
    assert fact[0].absence_request_id is None and fact[0].action.target=='intern'
    assert 'family' not in fact[0].model_dump_json() and 'Семейные' not in fact[0].text
    for user in DEMO_USERS:
        if user!=PETR:
            with pytest.raises(NotFound):
                run(clock.snooze_reminder(DEMO_USERS[user],fact[0].id))
    assert all('reason' not in e.payload for e in snapshot().events if e.type.startswith('absence_'))


def test_absence_day_shifts_only_open_items_once_even_after_restart_tick(store, snapshot):
    req=send(day=date(2026,11,12))
    before=snapshot().items
    decide(req)
    run(clock.advance_day(DEMO_USERS[ANYA],ANYA))
    first=snapshot()
    for id,item in before.items():
        delta=1 if item.intern_id==ANYA and item.status!='done' and item.due_day is not None else 0
        assert first.items[id].due_day == (item.due_day+delta if item.due_day is not None else None)
    today=[r for r in reminders(ANYA) if r.kind=='absence_today']
    assert len(today)==1
    run(clock.done_reminder(DEMO_USERS[ANYA],today[0].id))
    run(clock.cron_tick(SYSTEM_ACTOR))
    assert snapshot().items==first.items
    run(clock.advance_day(DEMO_USERS[ANYA],ANYA))
    assert snapshot().items==first.items


def test_rejected_absence_does_not_notify_mentor_or_shift(store, snapshot):
    req=send(day=date(2026,11,12))
    before=snapshot().items
    decide(req,approve=False)
    assert not any(r.kind=='absence_fact' for r in reminders(PETR))
    assert 'отклонён' in next(r for r in reminders(ANYA) if r.kind=='absence_decided').text
    run(clock.advance_day(DEMO_USERS[ANYA],ANYA))
    assert snapshot().items==before
    assert not any(r.kind=='absence_today' for r in reminders(ANYA))


def test_lead_snooze_uses_related_intern_day_and_reactivates(store):
    send(day=date(2026,11,15))
    r=next(r for r in reminders(OLGA) if r.kind=='absence_new')
    assert run(clock.snooze_reminder(DEMO_USERS[OLGA],r.id)).snooze_until_day==3
    run(clock.advance_day(DEMO_USERS['intern-ivan'],'intern-ivan'))
    assert next(v for v in reminders(OLGA) if v.id==r.id).status=='snoozed'
    run(clock.advance_day(DEMO_USERS[ANYA],ANYA))
    assert next(v for v in reminders(OLGA) if v.id==r.id).status=='active'


@pytest.mark.parametrize('intern,lead', [
    ('intern-anya', 'lead-olga'), ('intern-kirill', 'lead-olga'),
    ('intern-ivan', 'lead-sergey'), ('intern-liza', 'lead-sergey'),
])
def test_new_absence_notification_identifies_intern_without_reason(store, intern, lead):
    request = send(user=intern, day=date(2026, 11, 12), reason='family')
    notice, = [r for r in reminders(lead) if r.kind == 'absence_new']
    assert notice.text == f'Новая заявка на отгул: {DEMO_USERS[intern].name}, 12.11'
    assert notice.intern_id == intern and notice.absence_request_id == request.id
    assert 'family' not in notice.model_dump_json()
    assert not any(r.kind == 'absence_new' for r in reminders('lead-sergey' if lead == 'lead-olga' else 'lead-olga'))
