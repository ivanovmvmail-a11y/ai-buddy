"""Общие фикстуры. Все тесты работают без ключей и сети."""
import asyncio

import pytest

from app import main, rag
from app.agent import service
from app.config import settings
from app.llm import LLMReply, ToolCall, get_llm


class ScriptedLLM:
    """Поддельная модель: отдаёт заранее заданные ответы и запоминает, что ей прислали."""

    name = "scripted"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []  # [(messages, tools)]
        self.loops = []

    async def chat(self, messages, tools=None):
        self.calls.append((list(messages), tools))
        self.loops.append(asyncio.get_running_loop())
        item = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(item, Exception):
            raise item
        return item


def tool_reply(name, arguments=None, call_id="call_1"):
    return LLMReply(tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments or {})])


def text_reply(text):
    return LLMReply(content=text)


@pytest.fixture
def agent(monkeypatch):
    """Свежий агент (пустое хранилище действий) на каждый тест."""
    fresh = service.build_agent()
    monkeypatch.setattr(service, "agent", fresh)
    return fresh


@pytest.fixture
def use_llm(monkeypatch):
    def _use(*replies):
        llm = ScriptedLLM(replies)
        monkeypatch.setattr(service, "get_llm", lambda: llm)
        return llm

    return _use


@pytest.fixture
def client(monkeypatch, agent):
    monkeypatch.setattr(settings, "llm_provider", "echo")
    get_llm.cache_clear()
    yield main.create_app().test_client()
    get_llm.cache_clear()


def as_user(user_id):
    return {"X-User-Id": user_id}


@pytest.fixture(autouse=True)
def no_configured_database(monkeypatch):
    """Даже при локальном .env обычный набор тестов не подключается к живой БД."""
    monkeypatch.setattr(settings, "database_url", "")
    clear_cache = rag.get_service.cache_clear
    clear_cache()
    yield
    clear_cache()


def pytest_addoption(parser):
    parser.addoption("--rag-postgres", action="store_true", help="Test migration/pool on a disposable local Docker PostgreSQL")
    parser.addoption("--mcp-postgres", action="store_true", help="Run the shared onboarding suite on memory and a disposable PostgreSQL")
