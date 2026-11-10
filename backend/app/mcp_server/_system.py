"""Внутренний контекст системных задач; не инструмент/аргумент пользовательского API."""
from contextlib import contextmanager
from contextvars import ContextVar

from .errors import Forbidden

_system = ContextVar("onboarding_system", default=False)


@contextmanager
def system_call():
    token = _system.set(True)
    try:
        yield
    finally:
        _system.reset(token)


def require_system():
    if not _system.get():
        raise Forbidden("Операция доступна только системе")
