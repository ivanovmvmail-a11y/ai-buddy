"""Синтетическая самопроверка. Результаты только стажёру, карта навыков не меняется."""
from functools import cache
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from app.agent.users import Role
from app.rag.ingest import DEMO_DOCS, read_document
from . import drafts, events, storage
from ._domain import intern
from .errors import Conflict, NotFound
from .models import ActionDraft
from .self_check_models import BankQuestion, Question, ReviewedAnswer, SelfCheckResult, Submission, Topic

BANK_PATH = Path(__file__).with_name('seed') / 'self_check.json'
SOURCE_BASE = 'https://github.com/ivanovmvmail-a11y/ai-buddy/blob/main/backend/app/rag/demo_docs/'


@cache
def _bank() -> tuple[BankQuestion, ...]:
    source = json.loads(BANK_PATH.read_text(encoding='utf-8'))
    questions = tuple(BankQuestion.model_validate(q) for q in source['questions'])
    documents = {f'demo:{p.name}': read_document(p, f'demo:{p.name}') for p in DEMO_DOCS.glob('*.md')}
    if len({q.id for q in questions}) != len(questions):
        raise ValueError('Повтор id в банке самопроверки')
    for question in questions:
        document = documents.get(question.source_id)
        if document is None or document.team not in (None, question.team):
            raise ValueError('Недоступный источник самопроверки')
        if question.source_url != SOURCE_BASE + question.source_id.removeprefix('demo:'):
            raise ValueError('Неверная ссылка источника самопроверки')
    return questions


def _student(data, user):
    if user.role != Role.INTERN:
        raise NotFound()
    return intern(data, user.id)


def _questions(user, topic):
    # Submission также проверяет Topic; здесь отдельная проверка для чтения.
    from pydantic import TypeAdapter
    topic = TypeAdapter(Topic).validate_python(topic)
    questions = [q for q in _bank() if q.team == user.team and q.topic == topic]
    if not 2 <= len(questions) <= 3:
        raise Conflict('Для темы пока нет учебного набора')
    return questions


def _version(questions):
    return sha256(json.dumps([q.model_dump() for q in questions], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _result(data, user, result_id):
    result = data.self_check_attempts.get(result_id)
    if result is None or result.intern_id != user.id or result.team != user.team:
        raise NotFound()
    return result


async def get_questions(user_id: str, topic: Topic) -> list[Question]:
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        _student(data, user)
        return [Question.model_validate(q.model_dump(exclude={'team','correct_index','explanation'}))
                for q in _questions(user, topic)]


async def draft_answers(user_id: str, topic: Topic, answers: dict[str, int]) -> ActionDraft:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        _student(data, user)
        value = Submission(topic=topic, answers=answers)
        questions = _questions(user, value.topic)
        if set(value.answers) != {q.id for q in questions}:
            raise NotFound()
        if any(value.answers[q.id] >= len(q.options) for q in questions):
            raise Conflict('Выберите вариант из списка')
        return drafts.create(data, user, 'self_check.submit', {**value.model_dump(), 'bank_version': _version(questions)})


async def confirm_answers(user_id: str, draft_id: str) -> SelfCheckResult:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        _student(data, user)
        draft = drafts.owned(data, user, draft_id, 'self_check.submit')
        if draft.status == 'confirmed':
            return _result(data, user, draft.result_id).model_copy(deep=True)
        drafts.pending(draft)
        questions = _questions(user, draft.payload['topic'])
        if _version(questions) != draft.payload['bank_version']:
            raise Conflict('Учебный набор изменился; подготовьте ответы заново')
        review = [ReviewedAnswer(question_id=q.id, prompt=q.prompt, options=q.options,
            selected_index=draft.payload['answers'][q.id], correct_index=q.correct_index,
            explanation=q.explanation, source_id=q.source_id, source_url=q.source_url) for q in questions]
        result = SelfCheckResult(id=f'SC-{uuid4().hex}', intern_id=user.id, team=user.team,
            topic=draft.payload['topic'], completed_day=data.interns[user.id].current_day, review=review)
        data.self_check_attempts[result.id] = result
        drafts.finish(draft, result.id)
        events._record(data, user, 'self_check_completed', {'topic': result.topic})
        return result.model_copy(deep=True)


async def get_result(user_id: str, result_id: str) -> SelfCheckResult:
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        _student(data, user)
        return _result(data, user, result_id).model_copy(deep=True)


async def list_results(user_id: str) -> list[SelfCheckResult]:
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        _student(data, user)
        return [r.model_copy(deep=True) for r in data.self_check_attempts.values()
                if r.intern_id == user.id and r.team == user.team]
