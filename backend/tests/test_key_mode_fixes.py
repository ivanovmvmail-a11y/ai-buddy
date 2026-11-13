"""Проверка 13.11 в Docker с ключом GigaChat: уровень в ответах чата, сводки наставнику и руководителю, отмена отгула,
верный факт в сводке куратору, не больше двух источников. Всё — правила сервера, одинаковые для любой модели."""
from .conftest import text_reply
from .test_agent import run_agent
from .test_scenario_provider import demo_docs, scenario  # noqa: F401 — фикстуры: настоящие демо-документы

from app.agent.levels import level_for, skills_from, topic_of
from app.agent.service import cited_sources
from app.llm.scenario_provider import ScenarioProvider

SYSTEM = "Текущий пользователь: Аня Смирнова, роль: intern. Уровень по темам: git — новичок, sql — уверенно, ci — знаком."


def test_topic_and_level_from_question():
    assert topic_of("как создать ветку и отправить на ревью?") == "git"
    assert topic_of("как запулить код?") == "git"  # разговорное → pull request
    assert topic_of("у меня упал пайплайн") == "ci"
    assert topic_of("как написать select к базе данных") == "sql"
    assert topic_of("когда дейли?") is None
    assert topic_of("ветка упала на сборке") is None  # две темы — не угадываем
    assert skills_from(SYSTEM) == {"git": "novice", "sql": "confident", "ci": "familiar"}
    assert level_for("как создать ветку?", SYSTEM) == ("git", "novice")
    assert level_for("какой у меня уровень по git?", SYSTEM) is None
    assert level_for("как создать ветку?", "без профиля") is None


def test_same_question_different_depth_for_anya_and_kirill(demo_docs, agent, use_llm):
    llm = use_llm(text_reply("Создай ветку и открой pull request."), text_reply("Создай ветку и открой pull request."))
    anya = run_agent(agent, "intern-anya", text="как создать ветку и отправить изменения на ревью?").reply
    kirill = run_agent(agent, "intern-kirill", text="как создать ветку и отправить изменения на ревью?").reply
    assert anya.startswith("Git в твоей карте навыков пока новая тема — разберу по шагам.")
    assert kirill.startswith("Git ты знаешь уверенно — коротко")
    systems = [messages[0].content for messages, _ in llm.calls]
    assert "по шагам (3–6 коротких шагов)" in systems[0] and "2–3 предложения" in systems[1]


def test_no_depth_line_when_not_found_or_not_intern(demo_docs, agent, use_llm):
    use_llm(text_reply("В документах команды этого нет. Спроси наставника."), text_reply("Ветки — по шаблону."))
    assert not run_agent(agent, "intern-anya", text="как назвать ветку для git-хуков?").reply.startswith("Git")
    assert not run_agent(agent, "mentor-petr", text="как назвать ветку?").reply.startswith("Git")


def test_cancel_absence_is_honest_not_new_draft(agent, use_llm):
    llm = use_llm(text_reply("не нужна"))
    result = run_agent(agent, "intern-anya", text="отмени мой отгул")
    assert result.actions == [] and "не отменяю" in result.reply and "Ольга Новикова" in result.reply
    assert llm.calls == []


def test_level_change_requests_point_to_mentor(agent, use_llm):
    use_llm(text_reply("не нужна"))
    assert "Уровень по темам" in run_agent(agent, "mentor-petr", text="подними Ане уровень по git").reply
    assert "Это я уже знаю" in run_agent(agent, "intern-anya", text="подними мне уровень по git").reply
    assert "только наставник" in run_agent(agent, "lead-olga", text="поставь Ане уровень уверенно").reply


def test_compare_points_to_mentor_screen(agent, use_llm):
    use_llm(text_reply("не нужна"))
    assert "Сравнить планы" in run_agent(agent, "mentor-petr", text="покажи сравнение Ани и Кирилла").reply
    assert "Сравнить планы" not in run_agent(agent, "lead-olga", text="сравни Аню и Кирилла").reply


def test_overview_for_mentor_and_lead_from_data(agent, use_llm):
    llm = use_llm(text_reply("не нужна"))
    petr = run_agent(agent, "mentor-petr", text="как дела у моих стажёров?").reply
    olga = run_agent(agent, "lead-olga", text="какой прогресс у стажёров моей команды?").reply
    for reply in (petr, olga):
        assert reply.startswith("Стажёров не сравниваю") and "Аня" in reply and "Кирилл" in reply
        assert "Иван" not in reply  # чужая команда
    assert llm.calls == []


def test_viewer_summary_does_not_claim_items_closed():
    plan = {"intern_id": "intern-anya", "current_day": 2, "next_step": None, "waiting": [],
            "items": [{"id": "a", "status": "done"}, {"id": "b", "status": "not_started"}]}
    text = ScenarioProvider()._plan(plan, own=False).content
    assert "закрыто 1 из 2" in text and "закрыты" not in text
    plan["items"][1]["status"] = "done"
    assert "Недели 1–2 закрыты" in ScenarioProvider()._plan(plan, own=False).content
    plan["next_step"] = {"id": "c", "title": "Назначить 1:1"}
    assert "Твой следующий шаг в этом плане — «Назначить 1:1»" in ScenarioProvider()._plan(plan, own=False).content


def test_at_most_two_closest_sources():
    reply = "Открой пайплайн, найди первый красный шаг, прочитай лог ошибки, воспроизведи локально и сделай коммит."
    docs = [
        {"title": "Пайплайн", "content": "Открой пайплайн, найди первый красный шаг, прочитай лог ошибки, воспроизведи "
                                         "локально, сделай коммит."},
        {"title": "Ревью", "content": "Прочитай комментарии, сделай коммит, воспроизведи замечание локально."},
        {"title": "Глоссарий", "content": "Пайплайн — шаг ошибки лога коммит локально найди открой прочитай."},
        {"title": "Слабый", "content": "Открой документ, найди наставника, прочитай правила, сделай заметку."},
    ]
    titles = [s["title"] for s in cited_sources(reply, docs)]
    assert titles[0] == "Пайплайн" and len(titles) <= 2 and "Слабый" not in titles
