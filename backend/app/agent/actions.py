"""Действия, которые что-то меняют: черновик → подтверждение пользователем → выполнение → результат.

ТЗ: «Действие считается выполненным, если сервис или его имитация возвращает результат,
который помощник отображает и сохраняет». Здесь хранится и черновик, и итог.
Интерфейс ActionStore: в памяти (без базы) или таблица PostgreSQL — переживает перезапуск (SPEC 9).
"""
import threading
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field

ActionStatus = Literal["pending", "running", "done", "failed", "cancelled"]  # running — выполняется сейчас


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


class ActionStore(Protocol):
    """Хранилище действий. Реализации: InMemoryActionStore (тесты, без базы) и PostgreSQL (зона Codex, app/db).

    Все методы асинхронные: агент вызывает их из своего цикла, HTTP — через app.async_runner.run().
    `claim` — атомарный захват черновика перед выполнением: из нескольких одновременных «Подтвердить»
    выполняет только один, остальные получают None (аудит D1).
    """

    async def create(self, *, user_id: str, tool: str, title: str, params: dict[str, Any]) -> Action: ...
    async def get(self, action_id: str) -> Action | None: ...
    async def list_for(self, user_id: str) -> list[Action]: ...
    async def save(self, action: Action) -> Action: ...
    async def claim(self, action_id: str, user_id: str) -> Action | None: ...
    async def clear(self) -> None: ...


def new_action(*, user_id: str, tool: str, title: str, params: dict[str, Any]) -> Action:
    return Action(id=f"act_{uuid.uuid4().hex[:12]}", user_id=user_id, tool=tool, title=title, params=params)


class InMemoryActionStore:
    def __init__(self) -> None:
        self._items: dict[str, Action] = {}
        self._lock = threading.Lock()

    async def create(self, *, user_id: str, tool: str, title: str, params: dict[str, Any]) -> Action:
        action = new_action(user_id=user_id, tool=tool, title=title, params=params)
        with self._lock:
            self._items[action.id] = action
        return action.model_copy(deep=True)

    async def get(self, action_id: str) -> Action | None:
        with self._lock:
            action = self._items.get(action_id)
            return action.model_copy(deep=True) if action else None

    async def list_for(self, user_id: str) -> list[Action]:
        with self._lock:
            items = [a.model_copy(deep=True) for a in self._items.values() if a.user_id == user_id]
        return sorted(items, key=lambda a: a.created_at, reverse=True)

    async def save(self, action: Action) -> Action:
        action.updated_at = _now()
        with self._lock:
            self._items[action.id] = action.model_copy(deep=True)
        return action

    async def claim(self, action_id: str, user_id: str) -> Action | None:
        with self._lock:
            action = self._items.get(action_id)
            if action is None or action.user_id != user_id or action.status != "pending":
                return None
            action.status = "running"
            action.updated_at = _now()
            return action.model_copy(deep=True)

    async def clear(self) -> None:
        with self._lock:
            self._items.clear()
