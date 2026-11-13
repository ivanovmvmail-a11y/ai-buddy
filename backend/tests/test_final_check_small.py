"""Мелочи из финальной проверки «глазами эксперта» 13.11 (отчёт .plans/fable-final-check.md, раздел 4)."""
from .test_scenario_provider import ask, demo_docs, scenario  # noqa: F401 — фикстуры


def test_who_to_write_about_day_off_is_answer_not_draft(demo_docs):
    body = ask(demo_docs, "кому писать про отгул?")
    assert body["actions"] == [] and "руководител" in body["reply"] and "на какой день" in body["reply"]
    assert ask(demo_docs, "мне завтра к врачу")["actions"]  # просьба с датой — по-прежнему черновик


def test_code_for_me_is_refused_politely(demo_docs):
    reply = ask(demo_docs, "напиши за меня код сортировки на питоне")["reply"]
    assert reply.startswith("Код за тебя не пишу") and "Подскажи, пожалуйста" not in reply


def test_lost_intern_gets_calm_next_step(demo_docs):
    reply = ask(demo_docs, "я ничего не понимаю")["reply"]
    assert reply.startswith("Понимаю") and "Следующий шаг" in reply


def test_mentor_explain_says_whose_text(client):
    res = client.post("/plan/items/anya.w1.team-space/explained?intern_id=intern-anya", json={"kind": "explain"},
                      headers={"X-User-Id": "mentor-petr"})
    assert "Что стажёр прочитает в документе" in res.get_json()["text"]


def test_swagger_page_has_offline_fallback_and_light_background(client):
    html = client.get("/docs").get_data(as_text=True)
    assert "window.SwaggerUIBundle" in html and "openapi.json" in html and "background: #fff" in html
