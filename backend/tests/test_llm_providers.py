"""Перевод сообщений и инструментов в форматы GigaChat и OpenAI. Сеть не используется."""
from types import SimpleNamespace as NS

import pytest

from app import async_runner
from app.config import settings
from app.llm import Message, ToolCall, ToolSpec, get_llm
from app.llm import gigachat_provider as gc
from app.llm import openai_provider as oa
from app.llm.echo_provider import EchoProvider

SPEC = ToolSpec(name="create_reminder", description="Напоминание",
                parameters={"type": "object", "properties": {"text": {"type": "string"}}})
HISTORY = [
    Message(role="system", content="sys"),
    Message(role="user", content="напомни"),
    Message(role="assistant", tool_calls=[ToolCall(id="c1", name="create_reminder", arguments={"text": "привет"})]),
    Message(role="tool", name="create_reminder", tool_call_id="c1", content='{"ok": true}'),
]


class FakeAsync:
    def __init__(self, response):
        self.response = response
        self.payloads = []

    async def __call__(self, payload=None, **kwargs):
        self.payloads.append(payload if payload is not None else kwargs)
        return self.response


def bare(cls, client):
    provider = cls.__new__(cls)
    provider._client = client
    return provider


# --- GigaChat ---

def test_gigachat_messages_format():
    out = gc.to_gigachat_messages(HISTORY)
    assert out[2]["function_call"] == {"name": "create_reminder", "arguments": {"text": "привет"}}
    assert out[2]["functions_state_id"] == "c1"
    assert out[3] == {"role": "function", "name": "create_reminder", "content": '{"ok": true}'}
    assert gc.to_gigachat_functions([SPEC])[0]["parameters"]["type"] == "object"


@pytest.mark.parametrize("arguments", [{"text": "x"}, '{"text": "x"}'])
def test_gigachat_parses_function_call(arguments):
    msg = NS(content="", functions_state_id=None, function_call=NS(name="create_reminder", arguments=arguments))
    achat = FakeAsync(NS(choices=[NS(message=msg)]))
    provider = bare(gc.GigaChatProvider, NS(achat=achat))
    reply = async_runner.run(provider.chat(HISTORY, [SPEC]))
    assert reply.tool_calls[0].name == "create_reminder"
    assert reply.tool_calls[0].arguments == {"text": "x"}
    assert reply.tool_calls[0].id.startswith("call_")
    assert achat.payloads[0]["function_call"] == "auto"


def test_gigachat_plain_answer_without_tools():
    msg = NS(content="Привет!", functions_state_id=None, function_call=None)
    achat = FakeAsync(NS(choices=[NS(message=msg)]))
    reply = async_runner.run(bare(gc.GigaChatProvider, NS(achat=achat)).chat(HISTORY[:2]))
    assert reply.content == "Привет!" and reply.tool_calls == []
    assert "functions" not in achat.payloads[0]


def test_gigachat_init(monkeypatch):
    monkeypatch.setattr(settings, "gigachat_credentials", "")
    with pytest.raises(RuntimeError):
        gc.GigaChatProvider()
    monkeypatch.setattr(settings, "gigachat_credentials", "dGVzdDp0ZXN0")  # фиктивный тестовый ключ
    assert gc.GigaChatProvider().name == "gigachat"
    monkeypatch.setattr(gc, "DEFAULT_CA_FILE", gc.DEFAULT_CA_FILE.with_name("missing.cer"))
    assert gc.GigaChatProvider().name == "gigachat"


# --- OpenAI-совместимые ---

def test_openai_messages_format():
    out = oa.to_openai_messages(HISTORY)
    assert out[2]["tool_calls"][0]["function"] == {"name": "create_reminder", "arguments": '{"text": "привет"}'}
    assert out[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'}
    assert oa.to_openai_tools([SPEC])[0]["type"] == "function"


def test_openai_parse_arguments_is_safe():
    assert oa.parse_arguments('{"a": 1}') == {"a": 1}
    assert oa.parse_arguments("не json") == {}
    assert oa.parse_arguments("[1]") == {}
    assert oa.parse_arguments(None) == {}


def test_openai_parses_tool_calls():
    call = NS(id="t1", function=NS(name="create_reminder", arguments='{"text": "x"}'))
    create = FakeAsync(NS(choices=[NS(message=NS(content=None, tool_calls=[call]))]))
    provider = bare(oa.OpenAICompatibleProvider, NS(chat=NS(completions=NS(create=create))))
    reply = async_runner.run(provider.chat(HISTORY, [SPEC]))
    assert reply.content == ""
    assert reply.tool_calls == [ToolCall(id="t1", name="create_reminder", arguments={"text": "x"})]
    assert create.payloads[0]["tools"][0]["function"]["name"] == "create_reminder"


def test_openai_init(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")
    with pytest.raises(RuntimeError):
        oa.OpenAICompatibleProvider()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-not-real")
    assert oa.OpenAICompatibleProvider().name == "openai"


# --- выбор провайдера ---

@pytest.mark.parametrize("provider,cls", [("echo", EchoProvider), ("ECHO", EchoProvider),
                                          ("openai", oa.OpenAICompatibleProvider),
                                          ("gigachat", gc.GigaChatProvider)])
def test_get_llm_picks_provider(monkeypatch, provider, cls):
    monkeypatch.setattr(settings, "llm_provider", provider)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-not-real")
    monkeypatch.setattr(settings, "gigachat_credentials", "dGVzdDp0ZXN0")
    get_llm.cache_clear()
    try:
        assert isinstance(get_llm(), cls)
    finally:
        get_llm.cache_clear()


def test_echo_ignores_tools():
    reply = async_runner.run(EchoProvider().chat([Message(role="user", content="привет")], [SPEC]))
    assert "привет" in reply.content and reply.tool_calls == []
