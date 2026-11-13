"""«Память» (PR #45 Codex + Claude 13.11): вопрос наставнику → ответ → база знаний команды → ответ следующему."""
from .conftest import as_user
from .test_scenario_provider import ask, scenario  # noqa: F401 — фикстура сценарного режима

QUESTION = "где найти пароль от учебного стенда маршрутов каталога"
ANSWER = "Пароль от учебного стенда маршрутов каталога выдаёт Пётр Волков в канале команды, пиши petr@example.test."


def post(client, path, user, body=None):
    return client.post(path, json=body or {}, headers=as_user(user))


def questions(client, user):
    return client.get("/mentor/questions", headers=as_user(user)).get_json()["questions"]


def reminders(client, user):
    return client.get("/reminders", headers=as_user(user)).get_json()["reminders"]


def test_full_loop_next_intern_gets_answer(scenario):
    # Аня: в документах нет → отправляет вопрос наставнику
    assert "этого нет" in ask(scenario, QUESTION)["reply"]
    res = post(scenario, "/mentor/questions", "intern-anya", {"text": QUESTION})
    assert res.status_code == 201
    q = res.get_json()
    assert q["status"] == "pending" and q["mentor_id"] == "mentor-petr" and q["intern_name"] == "Аня Смирнова"

    # Пётр видит вопрос во входящих и уведомление «Ответить»
    assert [x["id"] for x in questions(scenario, "mentor-petr")][0] == q["id"]
    [note] = [r for r in reminders(scenario, "mentor-petr") if r["kind"] == "mentor_question"]
    assert note["action"]["label"] == "Ответить" and "Новый вопрос — Аня Смирнова" in note["text"]

    # Пётр отвечает и добавляет в базу знаний: имя и контакт вычищены
    done = post(scenario, f"/mentor/questions/{q['id']}/answer", "mentor-petr", {"text": ANSWER, "publish": True}).get_json()
    assert done["status"] == "answered" and done["publication_status"] == "published"
    assert "Пётр" not in done["public_content"] and "petr@example.test" not in done["public_content"]
    assert [r for r in reminders(scenario, "mentor-petr") if r["kind"] == "mentor_question"] == []
    [told] = [r for r in reminders(scenario, "intern-anya") if r["kind"] == "mentor_answer"]
    assert "ответил на твой вопрос" in told["text"]
    assert questions(scenario, "intern-anya")[0]["answer"] == ANSWER  # стажёр видит полный ответ

    # Кирилл (та же команда) спрашивает то же — бот отвечает сразу, наставник больше не нужен
    reply = ask(scenario, QUESTION, "intern-kirill")
    assert reply["reply"].startswith("Наставник уже отвечал") and "стенда маршрутов" in reply["reply"]
    assert reply["sources"] and reply["sources"][0]["title"].startswith("Ответ наставника")
    assert "Пётр" not in reply["reply"]
    # и может открыть его в «Источник»
    doc = scenario.get("/documents", query_string={"title": reply["sources"][0]["title"]},
                       headers=as_user("intern-kirill")).get_json()
    assert "стенда маршрутов" in doc["content"]

    # Иван — другая команда: ответ Платформы ему не достаётся
    assert "Наставник уже отвечал" not in ask(scenario, QUESTION, "intern-ivan")["reply"]
    assert scenario.get("/documents", query_string={"title": reply["sources"][0]["title"]},
                        headers=as_user("intern-ivan")).status_code == 404


def test_answer_without_publishing_then_publish(scenario):
    q = post(scenario, "/mentor/questions", "intern-anya", {"text": "как называется учебный чат стажёров"}).get_json()
    done = post(scenario, f"/mentor/questions/{q['id']}/answer", "mentor-petr",
                {"text": "Учебный чат стажёров называется «Песочница».", "publish": False}).get_json()
    assert done["publication_status"] == "not_requested"
    assert post(scenario, f"/mentor/questions/{q['id']}/answer", "mentor-petr", {"text": "ещё раз"}).status_code == 409
    assert post(scenario, f"/mentor/questions/{q['id']}/publish", "mentor-petr").get_json()["publication_status"] == "published"
    assert post(scenario, f"/mentor/questions/{q['id']}/publish", "mentor-petr").status_code == 409


def test_permissions(scenario):
    q = post(scenario, "/mentor/questions", "intern-anya", {"text": "вопрос Ани"}).get_json()
    # чужой наставник, другой стажёр, руководитель — вопроса для них нет
    assert q["id"] not in [x["id"] for x in questions(scenario, "mentor-maria")]
    assert q["id"] not in [x["id"] for x in questions(scenario, "intern-kirill")]
    assert post(scenario, f"/mentor/questions/{q['id']}/answer", "mentor-maria", {"text": "x"}).status_code == 404
    assert post(scenario, f"/mentor/questions/{q['id']}/answer", "intern-anya", {"text": "x"}).status_code == 404
    assert scenario.get("/mentor/questions", headers=as_user("lead-olga")).status_code == 404
    assert post(scenario, "/mentor/questions", "mentor-petr", {"text": "x"}).status_code == 404
    assert post(scenario, "/mentor/questions", "intern-anya", {"text": ""}).status_code == 422
