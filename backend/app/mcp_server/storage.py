"""Атомарный unit of work; PostgreSQL реализуется в T3, не выбирается молча."""
import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from functools import cache
import logging
from typing import Protocol

from .models import OnboardingData

log = logging.getLogger("ai_buddy.onboarding")


class OnboardingStore(Protocol):
    def transaction(self) -> AbstractAsyncContextManager[OnboardingData]:
        """Изолированный снимок: коммит всего состояния либо откат при исключении."""
        ...

    async def initialize(self, data: OnboardingData, *, reset: bool = False) -> None: ...


class InMemoryStore:
    def __init__(self, data: OnboardingData | None = None):
        self._data = (data or OnboardingData()).model_copy(deep=True)
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self):
        async with self._lock:
            snapshot = self._data.model_copy(deep=True)
            yield snapshot
            # Сохранённый снимок не разделяет изменяемые объекты с вызывающим кодом.
            self._data = snapshot.model_copy(deep=True)

    async def initialize(self, data: OnboardingData, *, reset: bool = False) -> None:
        async with self._lock:
            if reset or not self._data.interns:
                self._data = data.model_copy(deep=True)


@cache
def get_store() -> OnboardingStore:
    from .seed import load_seed

    log.warning("Onboarding T1 uses process-local memory; data is lost on restart (PostgreSQL: T3)")
    return InMemoryStore(load_seed())
