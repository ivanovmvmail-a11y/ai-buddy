"""Эксперимент 14.11: намерение стажёра определяет модель (INTENT_ROUTER=model), сервер выполняет готовыми обработчиками."""
import json

import pytest

from app.agent.intent import _parse, command_for
from app.config import settings
from app.llm.base import LLMReply

from .test_scenario_provider import ask


class RouterThenAnswer:
    """Поддельная модель: первый вызов — ответ распределителя (JSON), дальше — обычный ответ."""
    name = "fake"

    def __init__(self, intent: dict, answer: str = "Ответ модели по документам.") -> None:
        self.intent, self.answer, self.calls = intent, answer, []

    async def chat(self, messages, tools=None):
        self.calls.append(messages)
        if len(self.calls) == 1:
            return LLMReply(content=json.dumps(self.intent, ensure_ascii=False))
        return LLMReply(content=self.answer)


@pytest.fixture
def router(client, monkeypatch):
    monkeypatch.setattr(settings, "intent_router", "model")

    def use(intent: dict, answer: str = "Ответ модели по документам."):
        fake = RouterThenAnswer(intent, answer)
        monkeypatch.setattr("app.agent.service.get_llm", lambda: fake)
        return fake
    return use


def test_parse_accepts_json_inside_text():
    assert _parse('Вот: {"intent": "docs", "topic": null}')["intent"] == "docs"
    assert _parse("не JSON") is None and _parse('{"intent": "взлом"}') is None


@pytest.mark.parametrize("data,command", [
    ({"intent": "next_step"}, "что мне делать дальше?"),
    ({"intent": "explain_item", "topic": "git"}, "объясни пункт про git"),
    ({"intent": "access", "resource": "grafana"}, "оформи доступ к Grafana"),
    ({"intent": "my_requests"}, "мои заявки"),
])
def test_command_for_intents(data, command):
    assert command_for(data, "исходный вопрос").command == command


def test_docs_intent_skips_plan_rule(client, router):
    """«Что мне делать, если ревьюер молчит?» по словам ловилось «что мне делать» → сводка плана."""
    fake = router({"intent": "docs"}, "Напомни ревьюеру через день.")
    body = ask(client, "что мне делать, если ревьюер молчит?")
    assert "Следующий шаг" not in body["reply"] and len(fake.calls) == 2


def test_topic_intent_explains_practicum(client, router):
    router({"intent": "explain_item", "topic": "git"})
    body = ask(client, "что мне по гиту поделать")
    assert body["item_id"] == "anya.p.git" and "Практикум: Git" in body["reply"]


def test_access_intent_makes_draft_by_server(client, router):
    router({"intent": "access", "resource": "grafana"})
    body = ask(client, "можно мне графану посмотреть? доступа нет")
    assert body["actions"] and body["actions"][0]["params"]["resource_id"] == "grafana"


def test_policy_still_guards_foreign_data(client, router):
    """Чужие данные — правило сервера, что бы ни сказал распределитель: модель отвечать не зовётся."""
    fake = router({"intent": "docs"})
    reply = ask(client, "какой уровень по git у Кирилла?")["reply"]
    assert "другого стажёра" in reply and len(fake.calls) == 1  # только распределитель


def test_router_failure_falls_back_to_words(client, router):
    router({"intent": "непонятно"})
    assert "Следующий шаг" in ask(client, "что мне делать дальше?")["reply"]


def test_off_by_default(client, use_llm, monkeypatch):
    monkeypatch.setattr(settings, "intent_router", "")
    from .conftest import text_reply
    llm = use_llm(text_reply("x"))
    ask(client, "что мне делать дальше?")
    assert llm.calls == []  # сводка плана по правилу, без модели — как раньше
