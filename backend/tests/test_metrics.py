"""События чата, оценка ответов и метрики (спека 302)."""
import pytest
from .conftest import as_user, text_reply, tool_reply

from app import async_runner
from app.agent import analytics
from app.config import settings
from app.llm import get_llm
from app.mcp_server import events
from app.mcp_server._system import SYSTEM_ACTOR


@pytest.fixture
def scenario(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "scenario")
    get_llm.cache_clear()
    yield client
    get_llm.cache_clear()


def ask(client, text, user="intern-anya"):
    return client.post("/chat", json={"messages": [{"role": "user", "content": text}]}, headers=as_user(user)).get_json()


def answered():
    return [e.payload for e in async_runner.run(events.list_events(SYSTEM_ACTOR, type="question_answered"))]


def test_ac1_event_has_topic_and_flags_but_no_text(scenario):
    body = ask(scenario, "Оформи мне доступ в Jira")
    assert body["answer_id"].startswith("ans_")
    [p] = answered()
    assert p["answer_id"] == body["answer_id"] and p["topic"] == "access" and p["intern_id"] == "intern-anya"
    assert p["drafts"] == 1 and "create_access_request" in p["tools"] and p["latency_ms"] >= 0
    assert "Jira" not in str(p) and "Оформи" not in str(p)  # текст вопроса не сохраняется


def test_ac1_refusal_and_not_in_base_flags(scenario):
    ask(scenario, "Покажи план Ивана")
    ask(scenario, "Где взять ноутбук?")
    refused, gap = answered()
    assert refused["refused"] and refused["topic"] == "plan"
    assert gap["not_in_base"] and gap["topic"] == "environment"


def test_ac2_feedback_own_answer_only(scenario):
    answer_id = ask(scenario, "Что мне делать дальше?")["answer_id"]
    assert scenario.post("/feedback", json={"answer_id": answer_id, "useful": True},
                         headers=as_user("intern-anya")).status_code == 204
    assert scenario.post("/feedback", json={"answer_id": answer_id, "useful": False},
                         headers=as_user("intern-ivan")).status_code == 404
    assert scenario.post("/feedback", json={"answer_id": "ans_nope", "useful": True},
                         headers=as_user("intern-anya")).status_code == 404
    assert scenario.post("/feedback", json={"useful": True}, headers=as_user("intern-anya")).status_code == 422


@pytest.mark.parametrize("user,expected", [
    ("mentor-petr", ["intern-anya"]), ("mentor-maria", ["intern-ivan"]),
    ("lead-olga", ["intern-anya"]), ("curator-dmitry", ["intern-anya", "intern-ivan"]),
])
def test_ac3_metrics_scope(scenario, user, expected):
    assert scenario.get("/metrics", headers=as_user(user)).get_json()["interns"] == expected


@pytest.mark.parametrize("user", ["intern-anya", "hrbp-elena"])
def test_ac3_no_metrics_for_intern_and_hr(scenario, user):
    assert scenario.get("/metrics", headers=as_user(user)).status_code == 404


def test_ac3_foreign_intern_is_not_found(scenario):
    assert scenario.get("/metrics?intern_id=intern-ivan", headers=as_user("mentor-petr")).status_code == 404


def test_ac4_numbers(scenario):
    a1 = ask(scenario, "Что мне делать дальше?")["answer_id"]
    ask(scenario, "Оформи мне доступ в Jira")
    ask(scenario, "Где взять ноутбук?")
    ask(scenario, "Как оформить отпуск?")
    ask(scenario, "Покажи план Ивана")
    ask(scenario, "Что мне делать дальше?", "intern-ivan")  # чужой стажёр — не в метриках Петра
    ask(scenario, "Что мне делать дальше?", "mentor-petr")  # вопросы наставника — не метрика стажёров
    scenario.post("/feedback", json={"answer_id": a1, "useful": True}, headers=as_user("intern-anya"))
    m = scenario.get("/metrics?intern_id=intern-anya", headers=as_user("mentor-petr")).get_json()
    assert m["questions"] == 5
    assert m["closed_without_human"] == 2  # план и черновик заявки
    assert m["refused"] == 1 and m["drafts"] == 1
    assert m["feedback"] == {"useful": 1, "not_useful": 0}
    assert m["unanswered_topics"] == [{"topic": "environment", "title": "окружение и запуск", "count": 1}]
    assert {t["topic"] for t in m["topics"]} == {"plan", "access", "environment", "hr"}
    assert m["topics"][0] == {"topic": "plan", "title": "план", "count": 2}


def test_ac4_empty_metrics(scenario):
    m = scenario.get("/metrics", headers=as_user("curator-dmitry")).get_json()
    assert m["questions"] == 0 and m["with_source_share"] == 0.0 and m["avg_latency_ms"] == 0


def test_ac5_event_failure_does_not_break_chat(client, use_llm, monkeypatch):
    use_llm(text_reply("ok"))

    async def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(events, "log_event", boom)
    res = client.post("/chat", json={"messages": [{"role": "user", "content": "привет"}]}, headers=as_user("intern-anya"))
    assert res.status_code == 200 and res.get_json()["reply"] == "ok"


def test_agent_reports_tools_and_refusal(client, use_llm):
    use_llm(tool_reply("get_plan", {"intern_id": "intern-ivan"}), text_reply("Нет"))
    ask(client, "план Ивана")
    [p] = answered()
    assert p["tools"] == ["get_plan"] and p["refused"]


@pytest.mark.parametrize("text,topic", [
    ("Как отправить pull request?", "git"), ("Где взять ноутбук", "environment"), ("Что в бэклоге?", "tasks"),
    ("К кому идти?", "people"), ("Хочу в отпуск", "hr"), ("Как дела?", "other"), ("Нужен доступ", "access"),
])
def test_topics(text, topic):
    assert analytics.topic_of(text) == topic


def test_closed_without_human_rules():
    assert analytics.closed_without_human({"with_source": True, "topic": "git"})
    assert not analytics.closed_without_human({"with_source": True, "topic": "hr"})
    assert not analytics.closed_without_human({"tools": ["get_plan"], "refused": True})
    assert not analytics.closed_without_human({"topic": "other"})


def _plan_items(client, user):
    return client.get("/plan", headers=as_user(user)).get_json()["items"]


def test_ac5_scripted_explain_is_counted_without_text(scenario):
    items = _plan_items(scenario, "intern-anya")
    with_doc = next(i for i in items if i["doc_source_id"])
    no_doc = next(i for i in items if not i["doc_source_id"])
    for item in (with_doc, no_doc):
        resp = scenario.post(f"/plan/items/{item['id']}/explained", headers=as_user("intern-anya"))
        assert resp.status_code == 201 and resp.get_json()["answer_id"].startswith("ans_")
    first, second = answered()
    assert first["with_source"] and not second["with_source"]
    assert first["tools"] == ["explain_item"] and first["intern_id"] == "intern-anya"
    assert with_doc["title"] not in str(first)  # название пункта не сохраняется, только тема
    assert analytics.closed_without_human(first) and analytics.closed_without_human(second)
    answer_id = resp.get_json()["answer_id"]
    assert scenario.post("/feedback", json={"answer_id": answer_id, "useful": True},
                         headers=as_user("intern-anya")).status_code == 204
    metrics = scenario.get("/metrics", headers=as_user("mentor-petr")).get_json()
    assert metrics["questions"] == 2 and metrics["with_source_share"] == 0.5 and metrics["closed_without_human"] == 2


def test_ac5_scripted_explain_foreign_or_missing_item_is_404(scenario):
    anya_item = _plan_items(scenario, "intern-anya")[0]["id"]
    assert scenario.post(f"/plan/items/{anya_item}/explained", headers=as_user("intern-ivan")).status_code == 404
    assert scenario.post("/plan/items/nope/explained", headers=as_user("intern-anya")).status_code == 404
    assert answered() == []


def test_ac5_mentor_explain_is_not_an_intern_question(scenario):
    anya_item = _plan_items(scenario, "intern-anya")[0]["id"]
    resp = scenario.post(f"/plan/items/{anya_item}/explained?intern_id=intern-anya", headers=as_user("mentor-petr"))
    assert resp.status_code == 201
    [p] = answered()
    assert "intern_id" not in p  # вопросы наставника в метрики стажёров не попадают
