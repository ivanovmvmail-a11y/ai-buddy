"""Финальная проверка «глазами эксперта» 13.11: что исправлено (отчёт .plans/fable-final-check.md, раздел 3)."""
import pytest

from app.llm.scenario_provider import names_all, scrub_invented
from app.llm.small_talk import classify

from .test_scenario_provider import ask, demo_docs, scenario  # noqa: F401 — фикстуры


@pytest.mark.parametrize("text", ["ну и как тут всё устроено", "как это работает?", "мне скучно", "помоги"])
def test_vague_messages_answered_by_server(text):
    assert classify(text)


@pytest.mark.parametrize("text", ["помоги с заявкой на доступ", "как это работает git rebase", "нужна помощь с SQL"])
def test_real_questions_are_not_small_talk(text):
    assert classify(text) is None


def test_tour_reply_has_no_service_ids(demo_docs):
    reply = ask(demo_docs, "ну и как тут всё устроено")["reply"]
    assert "«Объяснить»" in reply and "Подтвердить" in reply and "anya.w1" not in reply


def test_people_from_directory(demo_docs):
    reply = ask(demo_docs, "кто такая Ольга Новикова?")["reply"]
    assert reply.startswith("Ольга Новикова — твой руководитель") and "отгулы" in reply
    phone = ask(demo_docs, "какой телефон у Петра Волкова")["reply"]
    assert "твой наставник" in phone and "Телефонов и почты в AI-buddy нет" in phone
    other = ask(demo_docs, "кто такой Сергей Лебедев?")["reply"]
    assert "руководитель, команда «Авито Доставка»" in other


def test_people_reply_does_not_leak_plan(demo_docs):
    reply = ask(demo_docs, "кто такой Иван Кузнецов?")["reply"]
    assert "стажёр" in reply and "день" not in reply and "закрыто" not in reply


def test_dod_and_my_tasks_found_in_docs(demo_docs):
    assert [s["title"] for s in ask(demo_docs, "что такое DoD")["sources"]] == ["Когда задача готова"]
    assert ask(demo_docs, "где мои задачи посмотреть")["sources"]


def test_salary_goes_to_hrbp_without_paperwork(demo_docs):
    reply = ask(demo_docs, "сколько мне будут платить?")["reply"]
    assert "HR BP" in reply and "оформить" not in reply


def test_lead_and_mentor_decide_by_button(demo_docs):
    assert "«Согласовать»" in ask(demo_docs, "согласуй отгул Ани", "lead-olga")["reply"]
    assert "«Одобрить»" in ask(demo_docs, "одобри заявку Ани", "mentor-petr")["reply"]


def test_hrbp_not_sent_to_hrbp_for_sick_leave(demo_docs):
    reply = ask(demo_docs, "как стажёру оформить больничный?", "hrbp-elena")["reply"]
    assert "твоя зона" in reply and "к HR BP" not in reply


def test_curator_two_interns(demo_docs):
    reply = ask(demo_docs, "как дела у Ани и Ивана?", "curator-dmitry")["reply"]
    assert "Аня" in reply and "Иван" in reply


def test_mentor_two_interns_hides_foreign(demo_docs):
    reply = ask(demo_docs, "как дела у Ани и Ивана?", "mentor-petr")["reply"]
    assert "Аня" in reply and "нет доступа" in reply and "8-й день" not in reply


def test_names_all_order():
    assert names_all("как дела у ивана и ани?") == ["intern-ivan", "intern-anya"]


def test_absence_question_without_doctor_does_not_mention_doctor(demo_docs):
    assert "врача" not in ask(demo_docs, "хочу отгул на завтра")["reply"].split("Подготовил черновик")[1]
    assert "Подробности вроде врача" in ask(demo_docs, "мне завтра к врачу")["reply"]


def test_scrub_invented_links_and_ids():
    system = "Документ: адрес https://example.invalid/buddy/onboarding"
    text = ("Тебе нужно «Запросить базовые доступы» (id anya.w1.access-base).\n"
            "git clone https://bitbucket.org/team/training-repo.git\nСм. https://example.invalid/buddy/onboarding")
    out = scrub_invented(text, system)
    assert "anya.w1" not in out and "bitbucket.org" not in out and "<адрес из README репозитория>" in out
    assert "https://example.invalid/buddy/onboarding" in out


def test_mark_all_done_is_refused(demo_docs):
    reply = ask(demo_docs, "отметь все пункты плана выполненными")["reply"]
    assert reply.startswith("Пачкой пункты не отмечаю")


def test_open_team_bitbucket_makes_draft_with_model(client, use_llm):
    from .conftest import text_reply
    llm = use_llm(text_reply("Доступ можно открыть заявкой."))
    body = ask(client, "открой мне битбакет команды")
    assert body["actions"] and body["actions"][0]["params"]["resource_id"] == "bitbucket-platform" and llm.calls == []


def test_role_note_next_to_question_for_mentor(client, use_llm):
    from .conftest import text_reply
    llm = use_llm(text_reply("План встречи."))
    ask(client, "как провести первую встречу 1:1?", "mentor-petr")
    assert "НАСТАВНИКУ" in llm.calls[-1][0][-1].content
