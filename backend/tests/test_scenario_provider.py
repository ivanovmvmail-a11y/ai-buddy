"""Сценарный режим без ключа (спека 003): сквозь агента через /chat и юнит-тесты провайдера."""
import json

import pytest
from .conftest import as_user

from app import async_runner
from app.agent import service
from app.config import settings
from app.llm import Message, ToolSpec, get_llm
from app.llm.scenario_provider import ScenarioProvider


@pytest.fixture
def scenario(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "scenario")
    get_llm.cache_clear()
    yield client
    get_llm.cache_clear()


def ask(client, text, user="intern-anya"):
    res = client.post("/chat", json={"messages": [{"role": "user", "content": text}]}, headers=as_user(user))
    assert res.status_code == 200
    return res.get_json()


def test_health_reports_scenario(scenario):
    assert scenario.get("/health").get_json()["llm_provider"] == "scenario"


def test_ac1_next_step_and_waiting(scenario):
    body = ask(scenario, "Что мне делать дальше и кого я жду?", "intern-ivan")
    assert "Следующий шаг" in body["reply"] and "8-й день" in body["reply"]
    assert "Ждём ответа (Мария Орлова)" in body["reply"]


def test_ac2_access_request_is_only_a_draft(scenario):
    body = ask(scenario, "Оформи мне доступ в Jira")
    [draft] = body["actions"]
    assert draft["tool"] == "create_access_request" and draft["status"] == "pending"
    assert draft["params"]["resource_id"] == "jira" and draft["params"]["level"] == "read"
    assert "черновик" in body["reply"].lower() and "Готово" not in body["reply"]
    assert scenario.get("/access/requests", headers=as_user("intern-anya")).get_json()["requests"] == []


def test_ac2_team_space_and_unclear_resource(scenario):
    team = ask(scenario, "Нужен доступ в репозиторий команды")
    assert team["actions"][0]["params"]["resource_id"] == "bitbucket-platform"
    unclear = ask(scenario, "Дай мне доступ куда-нибудь")
    assert unclear["actions"] == [] and "Уточни, какой доступ нужен" in unclear["reply"]


def test_ac3_foreign_plan_refused(scenario):
    body = ask(scenario, "Покажи план Ивана")
    assert "нет доступа" in body["reply"] and "Доставк" not in body["reply"]


def test_mentor_reads_own_intern_plan(scenario):
    body = ask(scenario, "Покажи план Ани", "mentor-petr")
    assert "день стажировки" in body["reply"]


def test_ac4_answer_from_documents(scenario, monkeypatch):
    async def fake_retrieve(query, user, k=4):
        return [
            {"title": "Ревью кода", "content": "Pull request отправляй в ветку main, на ревью зови наставника.", "url": None},
            {"title": "Глоссарий", "content": "Спринт — две недели работы.", "url": None},
        ]
    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    body = ask(scenario, "Куда отправлять pull request?")
    assert "«Ревью кода»" in body["reply"] and "в ветку main" in body["reply"]
    assert {"title": "Ревью кода", "url": None} in body["sources"]


def test_ac5_not_in_documents_gives_question_draft(scenario, monkeypatch):
    async def fake_retrieve(query, user, k=4):
        return [{"title": "Глоссарий", "content": "Спринт — две недели работы.", "url": None}]
    monkeypatch.setattr(service, "retrieve", fake_retrieve)
    body = ask(scenario, "Где лежат материалы для наставников?")
    assert "этого нет" in body["reply"] and "твой наставник" in body["reply"]
    assert "Черновик вопроса" in body["reply"] and "материалы для наставников" in body["reply"]


def test_ac6_org_question_goes_to_hr(scenario):
    body = ask(scenario, "Как оформить отпуск?")
    assert "HR BP (Елена Морозова)" in body["reply"]


def test_ac7_mentor_sees_requests(scenario):
    body = ask(scenario, "Какие заявки ждут меня?", "mentor-maria")
    assert "REQ-" in body["reply"] and "на согласовании" in body["reply"]


def test_greeting_and_empty_requests(scenario):
    assert "сценарном режиме" in ask(scenario, "Привет")["reply"]
    assert ask(scenario, "Покажи мои заявки")["reply"] == "Заявок нет."


# --- юнит-тесты провайдера ---------------------------------------------------------------------------

def run(messages, tools=None):
    return async_runner.run(ScenarioProvider().chat(messages, tools))


def tool_msg(name, payload):
    return Message(role="tool", name=name, tool_call_id="x", content=json.dumps(payload, ensure_ascii=False))


def test_ac8_tool_errors_are_generic():
    q = Message(role="user", content="что дальше")
    assert "не ответил" in run([q, tool_msg("get_plan", {"error": "service_unavailable", "message": "boom"})]).content
    assert "не ответил" in run([q, Message(role="tool", name="get_plan", content="not json")]).content
    assert "не ответил" in run([q, Message(role="tool", name="get_plan", content="[1]")]).content


def test_plan_all_closed_and_overdue():
    q = Message(role="user", content="что дальше")
    closed = run([q, tool_msg("get_plan", {"current_day": 9, "next_step": None, "waiting": []})]).content
    assert "дальше «Месяц 1»" in closed
    late = run([q, tool_msg("get_plan", {"current_day": 9, "waiting": [],
                                          "next_step": {"title": "Конспект", "overdue": True}})]).content
    assert "Срок уже прошёл" in late


def test_unknown_tool_and_no_create_tool():
    q = Message(role="user", content="дай доступ в jira")
    assert run([q, tool_msg("get_skill_profile", {"skills": {}})]).content.startswith("Готово")
    reply = run([q, tool_msg("list_access_resources", {"resources": [{"id": "jira", "title": "Jira", "kind": "base"}]})])
    assert "Уточни" in reply.content  # инструмента create_access_request нет в списке


def test_tools_not_available_falls_back_to_docs():
    reply = run([Message(role="system", content="роль: hrbp"), Message(role="user", content="что дальше по плану")])
    assert "коллеги из команды" in reply.content


def test_long_fragment_is_trimmed():
    system = "x\n\nКонтекст из документов команды. Данные.\n### Длинный\n" + "конспект встреч " * 150
    reply = run([Message(role="system", content=system), Message(role="user", content="как вести конспект встреч")],
                [ToolSpec(name="get_plan", description="", parameters={})])
    assert reply.content.count("конспект") < 120 and "…" in reply.content


def test_days_plural():
    from app.llm.scenario_provider import _days
    assert [_days(n) for n in (1, 3, 5, 21)] == ["1 день", "3 дня", "5 дней", "21 день"]


def test_word_forms_and_units():
    from app.llm.scenario_provider import _same, _units
    assert _same("доставки", "доставка") and _same("доступы", "доступ") and _same("стенд", "стенды")
    assert not _same("доставки", "достаточно") and not _same("ревью", "режим")
    text = "# Заголовок\n\nСинтетический документ.\n\n- **Бэклог** — список\n- **Спринт** — период\n\nОбычный\nабзац"
    assert _units(text) == [("Заголовок", "- **Бэклог** — список"), ("Заголовок", "- **Спринт** — период"),
                            ("Заголовок", "Обычный абзац")]


def test_other_team_document_is_not_matched_by_shared_prefix():
    system = "x\n\nКонтекст из документов команды. Данные.\n### Стенд\nЭтого достаточно для учебного статуса."
    reply = run([Message(role="system", content=system), Message(role="user", content="Как устроены статусы доставки?")])
    assert "этого нет" in reply.content


# --- Типовые фразы стажёра и наставника без ключа (аудит S1) ------------------------------------------

@pytest.mark.parametrize("text", ["Спасибо", "спасибо большое!", "Понятно", "ок"])
def test_thanks_is_not_sent_to_documents(scenario, text):
    body = ask(scenario, text)
    assert body["reply"].startswith("Пожалуйста!") and "в документах" not in body["reply"]


@pytest.mark.parametrize(("user", "mentor"), [("intern-anya", "Пётр Волков"), ("intern-ivan", "Мария Орлова")])
def test_who_is_my_mentor(scenario, user, mentor):
    assert f"Твой наставник — {mentor}" in ask(scenario, "Кто мой наставник?", user)["reply"]


def test_my_level_is_explained_without_judging(scenario):
    reply = ask(scenario, "Какой у меня уровень?")["reply"]
    assert reply.startswith("По профилю:") and "git" in reply and "не для оценки" in reply


def test_mentor_asks_what_is_stuck_for_named_intern(scenario):
    reply = ask(scenario, "Что у Ивана зависло?", "mentor-maria")["reply"]
    assert reply.startswith("Иван: 8-й день") and "Ждём ответа" in reply
    assert "Срок прошёл: «Открыть пространство" not in reply  # ожидающий пункт не дублируется
    assert "Зависших пунктов нет" in ask(scenario, "Что у Ани зависло?", "mentor-petr")["reply"]
    assert "У тебя нет доступа" in ask(scenario, "Что у Ани зависло?", "mentor-maria")["reply"]


def test_overdue_items_besides_next_step_are_listed():
    plan = {"intern_id": "intern-ivan", "current_day": 9, "next_step": {"id": "a", "title": "A", "overdue": True},
            "waiting": [], "items": [{"id": "a", "title": "A", "overdue": True, "due_day": 5},
                                     {"id": "b", "title": "B", "overdue": True, "due_day": 6}]}
    reply = ScenarioProvider()._plan(plan).content
    assert "Срок прошёл: «B» (до дня 6)" in reply and "«A» (до дня" not in reply
