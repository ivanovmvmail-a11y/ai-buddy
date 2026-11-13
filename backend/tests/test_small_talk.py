"""Разговорные сообщения, имена в падежах, «Объяснить» от лица наставника (проверка после чекпоинта 2, 13.11)."""
import pytest

from app import async_runner
from app.agent.explain import explain_item
from app.agent.onboarding_tools import plan_context
from app.agent.users import DEMO_USERS, by_gender, name_in
from app.llm.scenario_provider import _missing_text
from app.llm.small_talk import classify

from .conftest import as_user, text_reply

ANYA, PETR, OLGA = DEMO_USERS["intern-anya"], DEMO_USERS["mentor-petr"], DEMO_USERS["lead-olga"]


def chat(client, messages, user="intern-anya"):
    res = client.post("/chat", json={"messages": messages}, headers=as_user(user))
    assert res.status_code == 200
    return res.get_json()


@pytest.mark.parametrize(("text", "expected"), [
    ("Привет", "Привет, Аня! Чем помочь?"),
    ("привет!!!", "Привет, Аня!"),
    ("Здравствуйте", "Привет, Аня!"),
    ("доброе утро", "Привет, Аня!"),
    ("Привет, бот", "Привет, Аня!"),
    ("привет, как дела?", "У меня всё хорошо"),
    ("как дела", "У меня всё хорошо"),
    ("Спасибо", "Пожалуйста!"),
    ("спасибо тебе большое!", "Пожалуйста!"),
    ("спс", "Пожалуйста!"),
    ("ок", "Хорошо!"),
    ("понял", "Хорошо!"),
    ("ясно", "Хорошо!"),
    ("пока", "Пока!"),
    ("до завтра!", "Пока!"),
    ("кто ты?", "AI-buddy"),
    ("что ты умеешь", "AI-buddy"),
    ("ааааааа", "Не понял"),
    ("???", "Не понял"),
    ("👍", "Не понял"),
    ("фыва", "Не понял"),
    ("ты бесполезный", "Не полезно"),
])
def test_small_talk_never_reaches_model(client, use_llm, text, expected):
    """С ключом такие реплики раньше уходили модели — она продолжала прошлую тему и выдумывала (13.11)."""
    llm = use_llm()  # без ответов: любой вызов модели упадёт
    body = chat(client, [{"role": "user", "content": text}])
    assert expected in body["reply"] and llm.calls == []
    assert body["sources"] == [] and body["actions"] == []


def test_greeting_mid_conversation_does_not_continue_old_topic(client, use_llm):
    """Ровно случай со скриншота: после объяснения песочницы «Привет» — приветствие, а не git clone."""
    llm = use_llm()
    body = chat(client, [
        {"role": "user", "content": "Объясни пункт «Запустить песочницу объявлений»"},
        {"role": "assistant", "content": "По шагам — по разделу «Как поднять песочницу»…"},
        {"role": "user", "content": "Привет"},
    ])
    assert body["reply"].startswith("Привет, Аня!") and "git" not in body["reply"].lower() and llm.calls == []
    assert "Следующий шаг по плану" in body["reply"]


@pytest.mark.parametrize("text", ["привет, где взять рабочий ноутбук?", "спасибо, а что дальше по плану?",
                                  "ок, а как получить доступ к Jira?", "покажи план", "sql", "да", "ты тупой, где ноутбук?"])
def test_question_with_politeness_is_still_a_question(text):
    assert classify(text) is None


def test_greeting_for_mentor_offers_mentor_things(client, use_llm):
    llm = use_llm()
    reply = chat(client, [{"role": "user", "content": "Привет"}], "mentor-petr")["reply"]
    assert reply.startswith("Привет, Пётр!") and "твоих стажёров" in reply and llm.calls == []


def test_name_forms_and_gender():
    assert name_in(PETR, "dat") == "Петру Волкову" and name_in(PETR, "gen") == "Петра Волкова"
    assert name_in(None, "dat", "наставнику") == "наставнику"
    assert by_gender(ANYA, "ответил", "ответила") == "ответила" and by_gender(PETR, "ответил", "ответила") == "ответил"


def test_plan_context_gives_model_ready_name_forms(fresh_onboarding):
    """«обратись к наставнику Петра Волкова» (GigaChat, 13.11) — модель получает готовые падежи."""
    context = async_runner.run(plan_context(ANYA))
    assert "Пётр Волков — у Петра Волкова, к Петру Волкову, с Петром Волковым" in context
    assert "Стажёр — девушка" in context
    # Пункты наставника стажёру подтверждать не нужно (GigaChat велел «подтвердить» 1:1 и доступы).
    assert "«Назначить регулярные встречи 1:1»" in context and "стажёру подтверждать их не нужно" in context


def test_question_draft_speaks_in_users_gender():
    anya = "Текущий пользователь: Аня Смирнова, роль: intern, команда: Платформа объявлений."
    ivan = "Текущий пользователь: Иван Кузнецов, роль: intern, команда: Авито Доставка."
    assert "Я поискала в документах команды, но ответа не нашла" in _missing_text("Где столовая?", anya)
    assert "Я поискал в документах команды, но ответа не нашёл" in _missing_text("Где столовая?", ivan)


def _item_id(title, intern="intern-anya"):
    from app.mcp_server import checklist
    plan = async_runner.run(checklist.get_plan(DEMO_USERS[intern], intern))
    return next(i.id for i in plan.items if i.title == title)


def test_explain_own_item_for_mentor(fresh_onboarding):
    """Пётр нажал «Объяснить» у своего пункта в плане Кирилла — текст для него, а не для стажёра."""
    item = _item_id("Добавить стажёра в каналы Mattermost", "intern-kirill")
    body = async_runner.run(explain_item(PETR, "intern-kirill", item, "explain"))
    text = body["text"]
    assert "твой пункт" in text and "От тебя" not in text and "Пётр Волков" not in text
    assert "демо-данные" not in text and "Когда сделаешь — нажми «Готово»" in text
    assert "К кому идти, если не получается?" not in body["chips"]


def test_explain_mentor_item_for_intern(fresh_onboarding):
    item = _item_id("Добавить стажёра в каналы Mattermost")
    text = async_runner.run(explain_item(ANYA, "intern-anya", item, "explain"))["text"]
    assert "тебе ничего делать не нужно" in text and "напомни Петру Волкову" in text
    meeting = _item_id("Назначить регулярные встречи 1:1")
    text = async_runner.run(explain_item(ANYA, "intern-anya", meeting, "explain"))["text"]
    assert "От тебя — договориться о времени" in text


def test_explain_intern_item_for_mentor_and_steps_without_intern_lines(fresh_onboarding):
    item = _item_id("Запустить песочницу объявлений", "intern-kirill")
    text = async_runner.run(explain_item(PETR, "intern-kirill", item, "explain"))["text"]
    assert "пункт Кирилла Егорова" in text and "ты знаешь" not in text
    steps = async_runner.run(explain_item(PETR, "intern-kirill", item, "steps"))["text"]
    assert "Если застрял" not in steps and "Проверь себя" not in steps
    who = async_runner.run(explain_item(PETR, "intern-kirill", item, "who"))["text"]
    assert "помогаешь ты" in who and "твой наставник" not in who


def test_who_to_ask_skips_demo_disclaimer(fresh_onboarding):
    item = _item_id("Запустить песочницу объявлений")
    text = async_runner.run(explain_item(ANYA, "intern-anya", item, "who"))["text"]
    assert "вымышленные маршруты" not in text and "твой наставник, Пётр Волков" in text


def test_explain_practicum_has_no_disclaimer(fresh_onboarding, client):
    plan = async_runner.run(__import__("app.mcp_server.checklist", fromlist=["x"]).get_plan(ANYA, ANYA.id))
    practicum = next(i for i in plan.items if i.title.startswith("Практикум"))
    text = async_runner.run(explain_item(ANYA, "intern-anya", practicum.id, "explain"))["text"]
    assert "демо-данные" not in text.lower() and "не регламент" not in text


def test_model_still_answers_real_question(client, use_llm):
    llm = use_llm(text_reply("По документу «Регламент учебного код-ревью»: открой PR в основную ветку."))
    chat(client, [{"role": "user", "content": "Привет! Как оформить pull request?"}])
    assert len(llm.calls) == 1
