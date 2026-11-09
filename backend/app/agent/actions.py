"""Действия, которые что-то меняют: черновик → подтверждение пользователем → выполнение → результат.

ТЗ: «Действие считается выполненным, если сервис или его имитация возвращает результат,
который помощник отображает и сохраняет». Здесь хранится и черновик, и итог.
Хранилище пока в памяти процесса; интерфейс ActionStore позволит заменить его на таблицу в PostgreSQL.
"""
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ActionStatus = Literal["pending", "done", "failed", "cancelled"]


def _now() -> datetime:
    return datetime.now(UTC)


class Action(BaseModel):
    id: str
    user_id: str
    tool: str
    title: str
    params: dict[str, Any]
    status: ActionStatus = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class ActionStore:
    def __init__(self) -> None:
        self._items: dict[str, Action] = {}
        self._lock = threading.Lock()

    def create(self, *, user_id: str, tool: str, title: str, params: dict[str, Any]) -> Action:
        action = Action(id=f"act_{uuid.uuid4().hex[:12]}", user_id=user_id, tool=tool, title=title, params=params)
        with self._lock:
            self._items[action.id] = action
        return action

    def get(self, action_id: str) -> Action | None:
        with self._lock:
            return self._items.get(action_id)

    def list_for(self, user_id: str) -> list[Action]:
        with self._lock:
            items = [a for a in self._items.values() if a.user_id == user_id]
        return sorted(items, key=lambda a: a.created_at, reverse=True)

    def save(self, action: Action) -> Action:
        action.updated_at = _now()
        with self._lock:
            self._items[action.id] = action
        return action
