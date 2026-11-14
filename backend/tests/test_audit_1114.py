"""Полная проверка 14.11 (чистый Docker с ключом GigaChat): выдумки модели и ответы мимо темы."""
import pytest

from .conftest import text_reply
from .test_agent import run_agent
from .test_scenario_provider import ask, demo_docs, scenario  # noqa: F401 — фикстура сценарного режима

from app.agent.analytics import topic_of
from app.agent.service import readable_marks
from app.llm.scenario_provider import asks_next, scrub_reply

DOCS = "Обнови основную ветку командой `git pull`, затем создай ветку `git checkout -b <номер-задачи>`. `git push -u origin <имя>`"


@pytest.mark.parametrize("phrase", [
    "я всё сделала на этой неделе?", "я все сделал?", "что мне осталось сделать?", "я успеваю по плану?",
    "что ещё нужно сделать на этой неделе",
])
def test_progress_question_is_plan_summary(phrase):
    assert asks_next(phrase)


def test_progress_answer_comes_from_plan_not_model(agent, use_llm):
    # Модель отвечала «остался один пункт, до 5 ноября» при девяти открытых — теперь её не спрашиваем.
    llm = use_llm(text_reply("Остался один пункт, до 5 ноября."))
    reply = run_agent(agent, "intern-anya", text="я всё сделала на этой неделе?").reply
    assert "Недели 1–2: закрыто" in reply and "Следующий шаг" in reply and "ноября" not in reply
    assert llm.calls == []


@pytest.mark.parametrize("phrase", [
    "я боюсь задавать глупые вопросы наставнику", "стесняюсь спрашивать наставника, вдруг вопрос тупой",
    "неудобно дёргать наставника вопросами",
])
def test_fear_of_asking_gets_answer_about_asking(agent, use_llm, phrase):
    llm = use_llm(text_reply("не нужна"))
    reply = run_agent(agent, "intern-anya", text=phrase).reply
    assert reply.startswith("Спрашивать — нормально") and "Пётр Волков" in reply and "Следующий шаг" not in reply
    assert llm.calls == []


def test_fear_about_deadline_still_calm_plan(scenario):
    reply = ask(scenario, "боюсь, что не успею к сроку")["reply"]
    assert reply.startswith("Понимаю") and "Следующий шаг" in reply


def test_scrub_drops_invented_command_and_avito_claim():
    text = ("1. Создай pull request.\n   Пример: `git pull request --create feature/new`\n"
            "2. Обнови ветку: `git pull`.\n"
            "3. Создай ветку: `git checkout -b 123-fix`.\n"
            "4. Закоммить: `git commit -m \"текст\"`.\n"
            "5. Запусти: `make run`.\n"
            "6. В Авито CI запускается автоматически на каждый pull request.")
    cleaned = scrub_reply(text, set(), set(), context=DOCS)
    assert "pull request --create" not in cleaned and "make run" not in cleaned and "В Авито" not in cleaned
    assert "`git pull`" in cleaned and "`git checkout -b 123-fix`" in cleaned and "git commit -m" in cleaned
    assert "1. Создай pull request." in cleaned


def test_scrub_keeps_team_name_and_old_behaviour_without_context():
    text = "В Авито Доставке учебное отправление проходит пять статусов."
    assert scrub_reply(text, set(), set(), context="") == text
    assert scrub_reply("В Авито так принято.", set(), set()) == "В Авито так принято."  # без context — как раньше


def test_model_reply_loses_invented_parts(agent, use_llm):
    use_llm(text_reply("Отправь ветку. Пример: `git pull request --create x`. В Авито ревью занимает час."))
    reply = run_agent(agent, "intern-anya", text="как отправить код на ревью?").reply
    assert "--create" not in reply and "В Авито" not in reply


def test_readable_marks():
    text = readable_marks("Меню обновляет [имя удалено], его почта [контакт удалён].")
    assert text == "Меню обновляет ответственный коллега (контакт спроси у наставника)."
    assert readable_marks("Оно обновляется [удалённый контакт].") == "Оно обновляется (контакт спроси у наставника)."
    assert readable_marks("Пиши [имя удалено] или на [контакт удалён]") == \
        "Пиши ответственный коллега или на (контакт спроси у наставника)"


def test_about_team_is_answered_by_server_from_document(agent, use_llm):
    llm = use_llm(text_reply("Команда отвечает за техническую платформу Авито."))
    reply = run_agent(agent, "intern-anya", text="как устроена команда и чем она занимается?").reply
    assert "техническую платформу" not in reply
    assert llm.calls == []


def test_about_team_paragraph_with_source(demo_docs):
    body = ask(demo_docs, "как устроена команда и чем она занимается?")
    assert "Бумажный каталог" in body["reply"], body["reply"]
    assert [s["title"] for s in body["sources"]] == ["Платформа объявлений — о команде"]


def test_about_team_with_key_ignores_model_invention(demo_docs, use_llm):
    llm = use_llm(text_reply("Команда отвечает за техническую платформу Авито."))
    body = ask(demo_docs, "как устроена команда и чем она занимается?")
    assert "Бумажный каталог" in body["reply"] and "техническую платформу" not in body["reply"]
    assert llm.calls == []


@pytest.mark.parametrize("user, text, expected", [
    ("lead-olga", "согласуй отгул Ани", "на карточке заявки здесь, в чате"),
    ("mentor-petr", "одобри заявку Ани на доступ", "на карточке заявки здесь, в чате"),
])
def test_decisions_point_to_chat_cards(agent, use_llm, user, text, expected):
    use_llm(text_reply("не нужна"))
    assert expected in run_agent(agent, user, text=text).reply


@pytest.mark.parametrize("question, topic", [
    ("можно работать из дома?", "hr"), ("что такое CI и зачем он мне", "environment"),
    ("что мне осталось сделать?", "plan"), ("кто отвечает за деплой?", "environment"),
    ("как мне запулить свой код", "git"), ("кто мой куратор?", "people"), ("как проходит экватор?", "plan"),
])
def test_topics_less_other(question, topic):
    assert topic_of(question) == topic


def test_definition_question_always_cites_glossary():
    from app.agent.service import cited_sources
    docs = [{"title": "Review", "content": "CI must be green before review.", "url": None},
            {"title": "Glossary", "content": "# Terms\n- **PR** \u2014 pull request.\n- **CI, \u043f\u0430\u0439\u043f\u043b\u0430\u0439\u043d** \u2014 automatic checks.", "url": None}]
    robot = "CI is a robot tester that watches your code."
    assert cited_sources(robot, docs, "\u0447\u0442\u043e \u0442\u0430\u043a\u043e\u0435 CI \u0438 \u0437\u0430\u0447\u0435\u043c \u043e\u043d \u043c\u043d\u0435")[0]["title"] == "Glossary"
    assert cited_sources(robot, docs, "\u043e\u0431\u044a\u044f\u0441\u043d\u0438 \u0447\u0442\u043e \u0442\u0430\u043a\u043e\u0435 \u043f\u0430\u0439\u043f\u043b\u0430\u0439\u043d")[0]["title"] == "Glossary"
    assert cited_sources(robot, docs, "\u0447\u0442\u043e \u0442\u0430\u043a\u043e\u0435 kubernetes") == []
    assert cited_sources(robot, docs, "\u043f\u043e\u0447\u0435\u043c\u0443 \u0443\u043f\u0430\u043b CI") == []
    missing = "\u0412 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430\u0445 \u044d\u0442\u043e\u0433\u043e \u043d\u0435\u0442."
    assert cited_sources(missing, docs, "\u0447\u0442\u043e \u0442\u0430\u043a\u043e\u0435 CI") == []
