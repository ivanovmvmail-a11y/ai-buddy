"""Общий unit of work: чтение без копии журнала и атомарная запись."""
import asyncio
from collections.abc import Mapping, Sequence
from copy import deepcopy
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import cache
import logging
from typing import Protocol

from app.config import settings

from .models import OnboardingData

log = logging.getLogger("ai_buddy.onboarding")


class _ReadMap(Mapping):
    """Копируется только запрошенная запись, а не весь снимок/журнал."""
    def __init__(self, source):
        self._source = source

    def __getitem__(self, key):
        return self._source[key].model_copy(deep=True)

    def __iter__(self):
        return iter(self._source)

    def __len__(self):
        return len(self._source)


class _ReadEvents(Sequence):
    def __init__(self, source):
        self._source = source

    def __getitem__(self, index):
        if isinstance(index, slice):
            return [event.model_copy(deep=True) for event in self._source[index]]
        return self._source[index].model_copy(deep=True)

    def __len__(self):
        return len(self._source)


class OnboardingStore(Protocol):
    def transaction(self, *, include_events: bool = True, copy_on_commit: bool = True) -> AbstractAsyncContextManager[OnboardingData]:
        """Изолированный снимок: коммит всего состояния либо откат при исключении."""
        ...

    def read(self, *, include_events: bool = False) -> AbstractAsyncContextManager[OnboardingData]:
        """Доверенный сервис читает доменные данные и может дописать события просмотра."""
        ...

    async def initialize(self, data: OnboardingData, *, reset: bool = False) -> None: ...

    async def close(self) -> None: ...


class InMemoryStore:
    def __init__(self, data: OnboardingData | None = None):
        self._data = (data or OnboardingData()).model_copy(deep=True)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self, *, include_events: bool = True, copy_on_commit: bool = True):
        async with self._lock:
            if include_events:
                snapshot = self._data.model_copy(deep=True)
            else:
                snapshot = OnboardingData.model_construct(**{
                    name: deepcopy(getattr(self._data, name)) for name in OnboardingData.model_fields if name != "events"
                }, events=[])
            yield snapshot
            committed = snapshot.model_copy(deep=True) if copy_on_commit else snapshot
            if not include_events:
                # Старые события неизменяемы для сервиса; коммит добавляет только новые.
                self._data.events.extend(committed.events)
                object.__setattr__(committed, "events", self._data.events)
            self._data = committed

    @asynccontextmanager
    async def read(self, *, include_events: bool = False):
        async with self._lock:
            # Внутренний read-view с ленивыми Mapping/Sequence; публичные DTO не
            # разделяют изменяемые модели с хранилищем даже при ошибке читателя.
            view = OnboardingData.model_construct(**{
                name: _ReadMap(getattr(self._data, name)) for name in OnboardingData.model_fields if name != "events"
            }, events=_ReadEvents(self._data.events) if include_events else [])
            count = len(view.events) if include_events else 0
            yield view
            if not include_events:
                self._data.events.extend(view.events)
            else:
                assert len(view.events) == count, "Historical reads must not append events"

    async def initialize(self, data: OnboardingData, *, reset: bool = False) -> None:
        async with self._lock:
            if reset or not any(getattr(self._data, field) for field in OnboardingData.model_fields):
                self._data = data.model_copy(deep=True)

    async def close(self) -> None:
        pass


@cache
def get_store() -> OnboardingStore:
    from .seed import load_seed

    if settings.database_url:
        from .postgres import PostgresStore
        return PostgresStore(settings.database_url)
    log.warning("Onboarding uses process-local memory; data is lost on restart without DATABASE_URL")
    return InMemoryStore(load_seed())
