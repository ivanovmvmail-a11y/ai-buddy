"""Личные уведомления через существующий Reminder; один объект на повод."""
from uuid import NAMESPACE_URL, uuid5
from .models import Reminder
from . import events
from ._system import SYSTEM_ACTOR


def notification_id(kind, user_id, key):
    return 'REM-' + uuid5(NAMESPACE_URL, f'ai-buddy:{kind}:{user_id}:{key}').hex


def notify(data, user_id, intern_id, kind, key, text, target, *, day=None, topic=None, **links):
    id = notification_id(kind, user_id, key)
    if id in data.reminders:
        return None
    reminder = Reminder(id=id, user_id=user_id, intern_id=intern_id, kind=kind,
        text=text, action={'label': {'absence_pending': 'Напомнить', 'absence_new': 'Решить', 'skill_suggestion': 'Решить', 'mentor_question': 'Ответить'}.get(kind, 'Открыть'), 'target': target, 'topic': topic},
        created_day=day if day is not None else data.interns[intern_id].current_day, **links)
    data.reminders[id] = reminder
    events._record(data, SYSTEM_ACTOR, 'reminder_created', {
        'intern_id': intern_id, 'reminder_id': id, 'kind': kind, 'day': reminder.created_day,
    })
    return reminder


def complete(data, absence_request_id, kinds):
    for reminder in data.reminders.values():
        if reminder.absence_request_id == absence_request_id and reminder.kind in kinds:
            reminder.status, reminder.snooze_until_day = 'done', None
