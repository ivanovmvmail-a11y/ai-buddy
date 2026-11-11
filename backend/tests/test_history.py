"""Переписка переживает обновление страницы и смену пользователя (SPEC 9, аудит S6/D7)."""
from .conftest import as_user, text_reply

from app import async_runner
from app.agent import history


def chat(client, text, user="intern-anya"):
    return client.post("/chat", json={"messages": [{"role": "user", "content": text}]}, headers=as_user(user))


def get_history(client, user="intern-anya", query=""):
    res = client.get(f"/chat/history{query}", headers=as_user(user))
    assert res.status_code == 200
    return res.get_json()["messages"]


def test_chat_turn_is_saved_for_the_user_only(client, use_llm):
    use_llm(text_reply("Ответ модели"))
    answer_id = chat(client, "Как оформить PR?").get_json()["answer_id"]
    msgs = get_history(client)
    assert [(m["role"], m["content"]) for m in msgs] == [("user", "Как оформить PR?"), ("assistant", "Ответ модели")]
    assert msgs[1]["answer_id"] == answer_id and "user_id" not in msgs[1]
    assert get_history(client, "intern-ivan") == []  # чужая переписка не видна


def test_scripted_explanation_is_saved(client):
    items = client.get("/plan", headers=as_user("intern-anya")).get_json()["items"]
    item = next(i for i in items if i["title"] == "Запустить песочницу объявлений")
    client.post(f"/plan/items/{item['id']}/explained", json={"kind": "steps"}, headers=as_user("intern-anya"))
    user_msg, bot_msg = get_history(client)
    assert user_msg["content"] == "Как это сделать по шагам?"
    assert bot_msg["content"].startswith("По шагам") and bot_msg["scripted"] is True
    assert bot_msg["sources"][0]["title"] == "Платформа объявлений — как поднять песочницу"
    assert bot_msg["sources"][0]["url"].endswith("17-platform-sandbox-setup.md")


def test_limit_and_reset(client):
    for n in range(30):
        async_runner.run(history.record_turn("intern-anya", f"вопрос {n}", f"ответ {n}"))
    msgs = get_history(client, query="?limit=500")
    assert len(msgs) == history.HISTORY_LIMIT and msgs[-1]["content"] == "ответ 29"  # последние, старые сверху
    assert len(get_history(client, query="?limit=4")) == 4
    client.post("/demo/reset", headers=as_user("intern-anya"))
    assert get_history(client) == []


def test_history_failure_does_not_break_chat(client, use_llm, monkeypatch):
    async def broken(*args, **kwargs):
        raise RuntimeError("db down")
    monkeypatch.setattr(history, "record_turn", broken)
    use_llm(text_reply("Ответ"))
    assert chat(client, "Привет").status_code == 200
