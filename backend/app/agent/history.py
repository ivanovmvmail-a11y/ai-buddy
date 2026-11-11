"""Переписка пользователя с ботом (SPEC 9, аудит S6/D7): переживает обновление страницы и смену пользователя.

История — только для самого пользователя: другим она не выдаётся, в аналитику по-прежнему идут только темы.
Реализации: в памяти процесса (без базы) и PostgreSQL (зона Codex: `app.db.history.postgres_history_store`).
"""
import threading
import uuid
from datetime import UTC, datetime
from typing import Literal, Protocol

from pydantic import BaseModel, Field

HISTORY_LIMIT = 50


class ChatEntry(BaseModel):
    id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    user_id: str
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict] = Field(default_factory=list)  # [{"title", "url"}]
    answer_id: str | None = None  # ответ можно оценить «полезно / не полезно»
    scripted: bool = False  # ответ собран без модели (сценарный режим)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HistoryStore(Protocol):
    async def append(self, entry: ChatEntry) -> None: ...
    async def list(self, user_id: str, limit: int = HISTORY_LIMIT) -> list[ChatEntry]: ...  # старые сверху
    async def clear(self) -> None: ...


class InMemoryHistoryStore:
    def __init__(self) -> None:
        self._items: list[ChatEntry] = []
        self._lock = threading.Lock()

    async def append(self, entry: ChatEntry) -> None:
        with self._lock:
            self._items.append(entry.model_copy(deep=True))

    async def list(self, user_id: str, limit: int = HISTORY_LIMIT) -> list[ChatEntry]:
        with self._lock:
            own = [e.model_copy(deep=True) for e in self._items if e.user_id == user_id]
        return own[-limit:] if limit > 0 else []

    async def clear(self) -> None:
        with self._lock:
            self._items.clear()


def make_history_store() -> HistoryStore:
    """PostgreSQL, если есть база и адаптер (зона Codex), иначе — в памяти процесса."""
    try:
        from app.db.history import postgres_history_store  # появится в PR Codex
    except ImportError:
        return InMemoryHistoryStore()
    return postgres_history_store() or InMemoryHistoryStore()


history = make_history_store()


async def record_turn(user_id: str, question: str, reply: str, *, sources: list[dict] | None = None,
                      answer_id: str | None = None, scripted: bool = False) -> None:
    """Вопрос и ответ одной парой. Сбой записи истории ответ не ломает — вызывающий логирует."""
    await history.append(ChatEntry(user_id=user_id, role="user", content=question))
    await history.append(ChatEntry(user_id=user_id, role="assistant", content=reply, sources=sources or [],
                                   answer_id=answer_id, scripted=scripted))
