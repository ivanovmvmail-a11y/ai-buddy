"""Чекпоинт 2 (13.11): пункты плана из чата и «Сделать за меня» в один клик для простых доступов."""
import pytest

from .conftest import as_user


def chat(client, text, user="intern-anya"):
    res = client.post("/chat", json={"messages": [{"role": "user", "content": text}]}, headers=as_user(user))
    assert res.status_code == 200
    return res.get_json()


@pytest.mark.parametrize(("text", "item"), [
    ("объясни пункт про песочницу", "anya.w1.sandbox"),
    ("Объясни пункт «Завести конспект встреч с наставником»", "anya.w1.notes"),
    ("что за пункт про каналы mattermost?", "anya.w1.channels"),
])
def test_explain_item_from_chat(client, use_llm, text, item):
    llm = use_llm()
    body = chat(client, text)
    assert body["item_id"] == item and llm.calls == []
    assert body["mode"] is None and body["reply"].startswith("«")


def test_explain_general_question_still_goes_to_model(client, use_llm):
    from .conftest import text_reply
    llm = use_llm(text_reply("OKR — цели и ключевые результаты."))
    body = chat(client, "объясни, что такое OKR")
    assert body["item_id"] is None and len(llm.calls) == 1


def test_practice_from_chat_starts_practice_mode(client, use_llm):
    llm = use_llm()
    body = chat(client, "хочу сдать задание по гиту")
    assert body["mode"] == "practice" and body["item_id"] and "Создай учебную ветку" in body["reply"]
    assert "ты сделала" in body["reply"] and llm.calls == []  # Аня — в женском роде


def test_practice_without_open_tasks_is_honest(client, use_llm):
    use_llm()
    body = chat(client, "хочу сдать задание", "intern-kirill")  # у Кирилла Git — уверенно: практикума Git нет
    assert body["mode"] in (None, "practice")
    if body["mode"] is None:
        assert "нет открытых заданий" in body["reply"] or "Какое задание" in body["reply"]


def test_next_step_answer_carries_item(client, use_llm):
    use_llm()
    body = chat(client, "что мне делать дальше?")
    assert body["item_id"] == "anya.w1.access-base"


def _quick(client, resource, user="intern-anya", level="read"):
    return client.post("/actions", json={"tool": "create_access_request", "quick": True, "params": {
        "resource_id": resource, "level": level, "justification": "Для учебных задач стажировки"}},
        headers=as_user(user))


def test_quick_simple_access_is_granted_at_once(client):
    res = _quick(client, "jira")
    assert res.status_code == 201
    action = res.get_json()
    assert action["status"] == "done" and action["result"]["request"]["status"] == "granted"


def test_quick_team_space_stays_a_draft(client):
    action = _quick(client, "bitbucket-platform").get_json()
    assert action["status"] == "pending" and action["result"] is None


def test_quick_higher_rights_stay_a_draft(client):
    action = _quick(client, "jira", level="edit").get_json()
    assert action["status"] == "pending"


def test_quick_needs_the_same_rights_as_a_draft(client):
    assert _quick(client, "jira", user="mentor-petr").status_code == 403


def test_without_quick_flag_everything_is_a_draft(client):
    res = client.post("/actions", json={"tool": "create_access_request", "params": {
        "resource_id": "jira", "level": "read", "justification": "Для учебных задач стажировки"}},
        headers=as_user("intern-anya"))
    assert res.get_json()["status"] == "pending"


@pytest.mark.parametrize(("text", "topic"), [
    ("мне завтра к врачу", "requests"),
    ("объясни пункт про песочницу", "study"),
    ("хочу сдать задание по гиту", "study"),
    ("что мне делать дальше?", "assistant"),
    ("Привет", "assistant"),
    ("мои заявки", "requests"),
])
def test_answer_goes_to_its_chat_tab(client, use_llm, text, topic):
    """Чекпоинт 2: «разделите чаты» — сервер говорит, в какую вкладку ответ."""
    from .conftest import text_reply
    use_llm(text_reply("Заявок пока нет."))  # «мои заявки» с ключом отвечает модель
    assert chat(client, text)["topic"] == topic
