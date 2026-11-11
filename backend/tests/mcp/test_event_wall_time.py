"""S3: реальное время журнала, независимые виртуальные сроки/недельная сводка."""
from datetime import datetime, timezone
import pytest
from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist, clock, events
from app.mcp_server._system import SYSTEM_ACTOR
run=async_runner.run
WALL=datetime(2035,7,4,5,30,tzinfo=timezone.utc)

class WallClock(datetime):
    @classmethod
    def now(cls,tz=None):
        assert tz is timezone.utc
        return WALL

@pytest.mark.parametrize('actor',[DEMO_USERS['intern-anya'],DEMO_USERS['mentor-petr'],SYSTEM_ACTOR])
@pytest.mark.parametrize('payload',[{'intern_id':'intern-anya','day':4000},{'intern_id':'missing','day':1},{}])
def test_event_ts_uses_wall_utc_and_keeps_virtual_payload(store,edit,snapshot,monkeypatch,actor,payload):
    monkeypatch.setattr(events,'datetime',WallClock)
    edit(lambda data: events._record(data,actor,'test_clock',payload))
    result=snapshot().events[-1]
    assert result.ts==WALL and result.ts.utcoffset().total_seconds()==0
    assert result.payload==payload and result.user_id==actor.id


def test_request_reminder_threshold_snooze_and_completion_ignore_event_ts(store,monkeypatch,snapshot):
    monkeypatch.setattr(events,'datetime',WallClock)
    actor=DEMO_USERS['intern-anya']
    before=len(snapshot().events)
    request=run(access.create_request(actor,'bitbucket-platform','read','Синтетическая задача'))
    assert request.created_at!=WALL
    run(clock.advance_day(actor,actor.id))
    assert not [r for r in snapshot().reminders.values() if r.request_id==request.id]
    run(clock.advance_day(actor,actor.id))
    reminder=next(r for r in snapshot().reminders.values() if r.request_id==request.id)
    assert reminder.created_day==4
    assert run(clock.snooze_reminder(actor,reminder.id)).snooze_until_day==5
    run(clock.advance_day(actor,actor.id))
    assert snapshot().reminders[reminder.id].status=='active'
    run(access.decide_request(DEMO_USERS['mentor-petr'],request.id,True))
    assert snapshot().reminders[reminder.id].status=='done' and run(clock.get_day(actor,actor.id))==5
    assert all(e.ts==WALL for e in snapshot().events[before:])


def test_weekly_replay_uses_payload_day_for_waiting_age_even_after_later_decision(store,monkeypatch):
    monkeypatch.setattr(events,'datetime',WallClock)
    actor=DEMO_USERS['intern-anya']
    request=run(access.create_request(actor,'bitbucket-platform','read','Синтетическая задача'))
    for _ in range(5): run(clock.advance_day(actor,actor.id))
    summary=run(checklist.weekly_summary(actor,actor.id,1))
    item=next(i for i in summary['carry_over'] if i.id==request.plan_item_id)
    assert item.status=='waiting' and item.waiting_days==5
    assert item.updated_at==request.created_at
    for _ in range(2): run(clock.advance_day(actor,actor.id))
    run(access.decide_request(DEMO_USERS['mentor-petr'],request.id,True))
    assert run(checklist.weekly_summary(actor,actor.id,1))==summary
