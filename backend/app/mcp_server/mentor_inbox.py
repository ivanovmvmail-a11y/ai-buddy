"""Личные входящие наставника. Confirm-функции — доверенному UI после подтверждения человека."""
from datetime import datetime, timedelta, timezone
import logging
import re
from uuid import uuid4

from app import rag
from app.agent.users import DEMO_USERS, Role
from app.rag.storage import Document

from . import drafts, events, storage
from ._domain import intern
from ._system import SYSTEM_ACTOR
from .errors import Conflict, NotFound
from .mentor_models import AnswerInput, MentorQuestion, QuestionInput
from .models import ActionDraft, Reminder
from .notifications import notify

log = logging.getLogger("ai_buddy.mentor_inbox")


def _student(data, user):
    if user.role != Role.INTERN:
        raise NotFound()
    target = intern(data, user.id)
    mentor = DEMO_USERS.get(target.mentor_id)
    if mentor is None or mentor.role != Role.MENTOR:
        raise Conflict("Наставник не назначен")
    return target


def _question(data, user, question_id, *, answering=False):
    question = data.mentor_questions.get(question_id)
    if question is None:
        raise NotFound()
    target = intern(data, question.intern_id)
    mentor = user.role == Role.MENTOR and user.id == question.mentor_id == target.mentor_id
    own = user.role == Role.INTERN and user.id == question.intern_id
    if not mentor and (answering or not own):
        raise NotFound()
    if target.team != question.team:
        raise NotFound()
    return question


def _public_text(answer):
    # Только ответ, без вопроса/связи со стажёром; известные демо-имена и контакты удаляются.
    irregular = {'Аня': r'Ан(?:я|и|е|ю|ей|ею)', 'Пётр': r'П[её]тр[а-яё]*'}
    for user in DEMO_USERS.values():
        answer = re.sub(re.escape(user.id), '[идентификатор удалён]', answer, flags=re.IGNORECASE)
        for part in user.name.split():
            stem = part[:-1] if part.endswith(('а', 'я')) else part
            pattern = irregular.get(part, re.escape(stem).replace('ё', '[её]') + r'[а-яё]*')
            answer = re.sub(r'\b(?:' + pattern + r')\b', '[имя удалено]', answer, flags=re.IGNORECASE)
    answer = re.sub(r'\[имя удалено\](?:\s+\[имя удалено\])+', '[имя удалено]', answer)  # «Пётр Волков» → одна метка
    answer = re.sub(r'[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}', '[контакт удалён]', answer)
    return re.sub(r'(?<!\w)(?:\+?7|8)[ -]?(?:\(\d{3}\)|\d{3})[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?!\d)',
                  '[контакт удалён]', answer)


def publication_title(question: MentorQuestion) -> str:
    """Название ответа в базе знаний: «Ответ наставника, 13.11.2026» (дата по Москве)."""
    day = question.answered_at.astimezone(timezone(timedelta(hours=3))).date()
    return f'Ответ наставника, {day:%d.%m.%Y}'


async def draft_question(user_id: str, text: str) -> ActionDraft:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        target = _student(data, user)
        text = QuestionInput(text=text).text
        return drafts.create(data, user, 'mentor.send', {'text': text, 'mentor_id': target.mentor_id})


async def confirm_question(user_id: str, draft_id: str) -> MentorQuestion:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        target = _student(data, user)
        draft = drafts.owned(data, user, draft_id, 'mentor.send')
        if draft.status == 'confirmed':
            return _question(data, user, draft.result_id).model_copy(deep=True)
        drafts.pending(draft)
        if draft.payload['mentor_id'] != target.mentor_id:
            raise Conflict("Наставник изменился; подготовьте новый черновик")
        question = MentorQuestion(id=f'MQ-{uuid4().hex}', intern_id=user.id, mentor_id=target.mentor_id,
            team=target.team, question=draft.payload['text'], created_day=data.interns[user.id].current_day)
        data.mentor_questions[question.id] = question
        drafts.finish(draft, question.id)
        events._record(data, user, 'mentor_question_sent', {'status': 'pending'})
        # Наставник узнаёт сразу (колокольчик, кнопка «Ответить»), а не через день (Claude, 13.11).
        short = question.question if len(question.question) <= 120 else question.question[:117] + '…'
        notify(data, question.mentor_id, user.id, 'mentor_question', question.id,
               f'Новый вопрос — {user.name}: «{short}»', 'mentor_question', mentor_question_id=question.id)
        return question.model_copy(deep=True)


async def get_question(user_id: str, question_id: str) -> MentorQuestion:
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        return _question(data, user, question_id).model_copy(deep=True)


async def list_questions(user_id: str) -> list[MentorQuestion]:
    user = drafts.actor(user_id)
    if user.role not in (Role.INTERN, Role.MENTOR):
        raise NotFound()
    async with storage.get_store().read() as data:
        return [q.model_copy(deep=True) for q in data.mentor_questions.values()
                if q.team == intern(data, q.intern_id).team and
                ((user.role == Role.INTERN and q.intern_id == user.id)
                or (user.role == Role.MENTOR and q.mentor_id == user.id
                    and intern(data, q.intern_id).mentor_id == user.id))]


def _with_topic(content: str, topic: str | None) -> str:
    """Тема от наставника — заголовком над ответом: по ней поиск находит ответ, даже если ответ другими словами
    («Меню — в канале…» на «где меню столовой?»). Тему пишет и видит наставник (по умолчанию интерфейс подставляет
    вопрос без имён); без темы публикуется только ответ, как раньше. Найдено на финальной проверке 13.11."""
    topic = re.sub(r'\s+', ' ', _public_text(topic or '')).strip().lstrip('#').strip()[:200]
    return f'## {topic}\n\n{content}' if topic else content


async def draft_answer(user_id: str, question_id: str, text: str, publish: bool = False,
                       topic: str | None = None) -> ActionDraft:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        question = _question(data, user, question_id, answering=True)
        if question.status != 'pending':
            raise Conflict("На вопрос уже ответили")
        value = AnswerInput(text=text, publish=publish)
        return drafts.create(data, user, 'mentor.answer', {'question_id': question.id, 'text': value.text,
            'publish': value.publish,
            'public_content': _with_topic(_public_text(value.text), topic) if value.publish else None})


async def confirm_answer(user_id: str, draft_id: str) -> MentorQuestion:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        draft = drafts.owned(data, user, draft_id, 'mentor.answer')
        question = _question(data, user, draft.payload['question_id'], answering=True)
        if draft.status != 'confirmed':
            drafts.pending(draft)
            if question.status != 'pending':
                raise Conflict("На вопрос уже ответили")
            question.status, question.answer = 'answered', draft.payload['text']
            question.answered_day = data.interns[question.intern_id].current_day
            question.answered_at = datetime.now(timezone.utc)
            if draft.payload['publish']:
                question.public_content = draft.payload['public_content']
                question.publication_status, question.source_id = 'pending', f'mentor-answer:{uuid4().hex}'
            for reminder in data.reminders.values():
                if reminder.mentor_question_id == question.id and reminder.status != 'done':
                    reminder.status, reminder.snooze_until_day = 'done', None
                    events._record(data, SYSTEM_ACTOR, 'mentor_question_reminder_completed', {'kind': 'mentor_question'})
            drafts.finish(draft, question.id)
            events._record(data, user, 'mentor_question_answered', {'status': 'answered'})
            notify(data, question.intern_id, question.intern_id, 'mentor_answer', question.id,
                   f'{user.name} ответил на твой вопрос', 'mentor_question')
        result = question.model_copy(deep=True)
    return await retry_publication(user_id, result.id) if result.publication_status == 'pending' else result


async def draft_publication(user_id: str, question_id: str, topic: str | None = None) -> ActionDraft:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        question = _question(data, user, question_id, answering=True)
        if question.status != 'answered' or question.publication_status != 'not_requested':
            raise Conflict("Публикация недоступна")
        return drafts.create(data, user, 'mentor.publish', {'question_id': question.id, 'public_content': _with_topic(_public_text(question.answer), topic)})


async def confirm_publication(user_id: str, draft_id: str) -> MentorQuestion:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        draft = drafts.owned(data, user, draft_id, 'mentor.publish')
        question = _question(data, user, draft.payload['question_id'], answering=True)
        if draft.status != 'confirmed':
            drafts.pending(draft)
            if question.status != 'answered' or question.publication_status != 'not_requested':
                raise Conflict("Публикация недоступна")
            question.publication_status, question.source_id = 'pending', f'mentor-answer:{uuid4().hex}'
            question.public_content = draft.payload['public_content']
            drafts.finish(draft, question.id)
        question_id = question.id
    return await retry_publication(user_id, question_id)


async def retry_publication(user_id: str, question_id: str) -> MentorQuestion:
    """Повтор уже подтверждённой публикации; не создаёт разрешение на публикацию."""
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        question = _question(data, user, question_id, answering=True).model_copy(deep=True)
    if question.publication_status == 'not_requested':
        raise Conflict("Публикация не подтверждена")
    if question.publication_status == 'published':
        return question
    try:
        service = rag.get_service() or rag.get_memory_service()
        await service.ingest(Document(source_id=question.source_id, title=publication_title(question),
                                      content=question.public_content, team=question.team))
    except Exception as error:
        log.warning('Mentor knowledge publication pending (%s)', type(error).__name__)
        return question
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        current = data.mentor_questions.get(question_id)
        stale = current is None or current.source_id != question.source_id
        if not stale:
            current = _question(data, user, question_id, answering=True)
            if current.publication_status != 'published':
                current.publication_status = 'published'
                events._record(data, user, 'mentor_answer_published', {'status': 'published'})
            result = current.model_copy(deep=True)
    if stale:
        await service.store.delete(question.source_id)
        raise NotFound()
    return result


def tick_questions(data, day=None, intern_ids=None):
    created = []
    by_question = {r.mentor_question_id: r for r in data.reminders.values() if r.mentor_question_id}
    for question in data.mentor_questions.values():
        if intern_ids is not None and question.intern_id not in intern_ids:
            continue
        if question.status != 'pending':
            continue
        current = day if day is not None else data.interns[question.intern_id].current_day
        reminder = by_question.get(question.id)
        if reminder is not None:
            if reminder.status == 'snoozed' and reminder.snooze_until_day is not None and current >= reminder.snooze_until_day:
                reminder.status, reminder.snooze_until_day = 'active', None
                events._record(data, SYSTEM_ACTOR, 'mentor_question_reminder_reactivated', {'kind': 'mentor_question'})
            continue
        if current - question.created_day <= 1:
            continue
        reminder = Reminder(id=f'REM-{uuid4().hex}', user_id=question.mentor_id, mentor_question_id=question.id,
                            kind='mentor_question', intern_id=question.intern_id,
                            action={'label': 'Ответить', 'target': 'mentor_question', 'topic': None},
                            text='Во входящих есть вопрос без ответа больше дня.', created_day=current)
        data.reminders[reminder.id] = reminder
        created.append(reminder)
        events._record(data, SYSTEM_ACTOR, 'mentor_question_reminder_created', {'kind': 'mentor_question', 'day': current})
    return created
