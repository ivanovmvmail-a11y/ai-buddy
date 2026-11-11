"""Серверные черновики. Confirm-функции сервисов вызываются только доверенным UI после клика."""
from uuid import uuid4

from app.agent.users import DEMO_USERS, User

from . import storage
from .errors import Conflict, NotFound
from .models import ActionDraft


def actor(user_id: str) -> User:
    user = DEMO_USERS.get(user_id)
    if user is None:
        raise NotFound()
    return user


def create(data, user: User, action: str, payload: dict) -> ActionDraft:
    draft = ActionDraft(id=f"DRAFT-{uuid4().hex}", owner_id=user.id, action=action, payload=payload)
    data.drafts[draft.id] = draft
    return draft.model_copy(deep=True)


def owned(data, user: User, draft_id: str, action: str | None = None) -> ActionDraft:
    draft = data.drafts.get(draft_id)
    if draft is None or draft.owner_id != user.id or (action is not None and draft.action != action):
        raise NotFound()
    return draft


def pending(draft: ActionDraft) -> None:
    if draft.status != "pending":
        raise Conflict("Черновик уже исполнен или отменён")


def finish(draft: ActionDraft, result_id: str) -> None:
    draft.status, draft.result_id = "confirmed", result_id


async def get_draft(user_id: str, draft_id: str) -> ActionDraft:
    user = actor(user_id)
    async with storage.get_store().read() as data:
        return owned(data, user, draft_id).model_copy(deep=True)


async def cancel_draft(user_id: str, draft_id: str) -> ActionDraft:
    user = actor(user_id)
    async with storage.get_store().transaction(include_events=False, copy_on_commit=False) as data:
        draft = owned(data, user, draft_id)
        pending(draft)
        draft.status = "cancelled"
        return draft.model_copy(deep=True)


async def invoke_by_id(user: User, operation, *args, **kwargs):
    """Адаптер для общего обработчика ошибок MCP, user берётся из привязки процесса."""
    return await operation(user.id, *args, **kwargs)
