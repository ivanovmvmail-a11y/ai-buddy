"""Один постоянный event loop в фоновом потоке для асинхронного кода (LLM, RAG, MCP).

Flask обрабатывает запросы синхронно. Если запускать корутины через asyncio.run()
или `async def`-вьюхи Flask, на каждый запрос создаётся новый loop, а долгоживущие
клиенты (GigaChat, OpenAI, httpx) остаются привязаны к первому — и падают
с «Event loop is closed». Поэтому вся асинхронщина выполняется в одном loop.
"""
import asyncio
import sys
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_lock = threading.Lock()


def _new_loop() -> asyncio.AbstractEventLoop:
    # На Windows new_event_loop() даёт ProactorEventLoop, а async-psycopg с ним не работает.
    if sys.platform == "win32":
        return asyncio.SelectorEventLoop()
    return asyncio.new_event_loop()


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _lock:
        if _loop is None or _loop.is_closed():
            _loop = _new_loop()
            threading.Thread(target=_loop.run_forever, name="async-runner", daemon=True).start()
        return _loop


def run(coro: Coroutine[Any, Any, T], timeout: float | None = 120) -> T:
    """Выполнить корутину в общем loop и дождаться результата из синхронного кода."""
    return asyncio.run_coroutine_threadsafe(coro, _get_loop()).result(timeout)
