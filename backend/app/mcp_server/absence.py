"""Имитация отгула на один день. Confirm вызывает доверенный UI после клика человека."""
from datetime import date, timedelta
from uuid import uuid4
from app.agent.users import DEMO_USERS, Role
from . import drafts, events, storage
from ._domain import intern
from .absence_models import AbsenceFact, AbsenceInput, AbsenceReason, AbsenceRequest, DecisionInput
from .errors import Conflict, NotFound
from .models import ActionDraft


def _student(data, user):
    if user.role != Role.INTERN:
        raise NotFound()
    target = intern(data, user.id)
    lead = DEMO_USERS.get(target.lead_id)
    if lead is None or lead.role != Role.LEAD or lead.team != target.team:
        raise Conflict('Руководитель команды не назначен')
    return target


def _today(data, intern_id):
    state = data.interns[intern_id]
    return state.start_date + timedelta(days=state.current_day - 1)


def _available(data, user, day):
    if day < _today(data, user.id):
        raise Conflict('Отгул нельзя оформить задним числом')
    if any(r.intern_id == user.id and r.day == day and r.status != 'rejected' for r in data.absence_requests.values()):
        raise Conflict('Отгул на этот день уже запрошен')


def _request(data, user, request_id, *, deciding=False):
    request = data.absence_requests.get(request_id)
    if request is None:
        raise NotFound()
    target = intern(data, request.intern_id)
    lead = user.role == Role.LEAD and user.id == request.lead_id == target.lead_id and user.team == target.team
    own = user.role == Role.INTERN and user.id == request.intern_id
    if target.team != request.team or (not lead and (deciding or not own)):
        raise NotFound()
    return request


async def draft_absence(user_id: str, day: date, reason: AbsenceReason) -> ActionDraft:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        target = _student(data, user)
        value = AbsenceInput(day=day, reason=reason)
        _available(data, user, value.day)
        return drafts.create(data, user, 'absence.send', {**value.model_dump(mode='json'), 'lead_id': target.lead_id})


async def confirm_absence(user_id: str, draft_id: str) -> AbsenceRequest:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        target = _student(data, user)
        draft = drafts.owned(data, user, draft_id, 'absence.send')
        if draft.status == 'confirmed':
            return _request(data, user, draft.result_id).model_copy(deep=True)
        drafts.pending(draft)
        if draft.payload['lead_id'] != target.lead_id:
            raise Conflict('Руководитель изменился; подготовьте новый черновик')
        value = AbsenceInput(day=draft.payload['day'], reason=draft.payload['reason'])
        _available(data, user, value.day)
        request = AbsenceRequest(id=f'ABS-{uuid4().hex}', intern_id=user.id, lead_id=target.lead_id,
            team=target.team, created_day=data.interns[user.id].current_day, **value.model_dump())
        data.absence_requests[request.id] = request
        drafts.finish(draft, request.id)
        events._record(data, user, 'absence_requested', {'status': 'pending'})
        return request.model_copy(deep=True)


async def get_request(user_id: str, request_id: str) -> AbsenceRequest:
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        return _request(data, user, request_id).model_copy(deep=True)


async def list_requests(user_id: str) -> list[AbsenceRequest]:
    user = drafts.actor(user_id)
    if user.role not in (Role.INTERN, Role.LEAD):
        raise NotFound()
    async with storage.get_store().read() as data:
        result = []
        for request in data.absence_requests.values():
            try:
                visible = _request(data, user, request.id)
            except NotFound:
                continue
            result.append(visible.model_copy(deep=True))
        return result


async def draft_decision(user_id: str, request_id: str, approve: bool) -> ActionDraft:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        request = _request(data, user, request_id, deciding=True)
        if request.status != 'pending':
            raise Conflict('Заявка уже рассмотрена')
        value = DecisionInput(approve=approve)
        return drafts.create(data, user, 'absence.decide', {'request_id': request.id, 'approve': value.approve})


async def confirm_decision(user_id: str, draft_id: str) -> AbsenceRequest:
    user = drafts.actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        draft = drafts.owned(data, user, draft_id, 'absence.decide')
        request = _request(data, user, draft.payload['request_id'], deciding=True)
        if draft.status != 'confirmed':
            drafts.pending(draft)
            if request.status != 'pending':
                raise Conflict('Заявка уже рассмотрена')
            request.status = 'approved' if draft.payload['approve'] else 'rejected'
            request.decided_day = data.interns[request.intern_id].current_day
            drafts.finish(draft, request.id)
            events._record(data, user, 'absence_decided', {'status': request.status})
        return request.model_copy(deep=True)


async def list_absence_facts(user_id: str, intern_id: str) -> list[AbsenceFact]:
    user = drafts.actor(user_id)
    async with storage.get_store().read() as data:
        target = intern(data, intern_id)
        if user.role != Role.MENTOR or target.mentor_id != user.id or target.team != user.team:
            raise NotFound()
        return [AbsenceFact(intern_id=target.id, day=r.day) for r in data.absence_requests.values()
                if r.intern_id == target.id and r.team == target.team and r.status == 'approved']
