"""GET /documents: текст документа из «Источник» — только общий или своей команды (проверка 12.11)."""
from .conftest import as_user


def get(client, title, user="intern-anya"):
    return client.get("/documents", query_string={"title": title}, headers=as_user(user))


def test_common_document_for_everyone(client):
    for user in ("intern-anya", "intern-ivan", "mentor-petr", "hrbp-elena"):
        res = get(client, "Глоссарий стажировки", user)
        assert res.status_code == 200
        body = res.get_json()
        assert body["team"] is None and "Pull request" in body["content"] and "---" not in body["content"][:5]


def test_own_team_document(client):
    body = get(client, "Платформа объявлений — о команде").get_json()
    assert body["team"] == "Платформа объявлений" and "Дейли" in body["content"]


def test_other_team_document_is_hidden(client):
    res = get(client, "Платформа объявлений — о команде", user="intern-ivan")
    assert res.status_code == 404 and "Дейли" not in res.get_data(as_text=True)
    assert get(client, "Авито Доставка — статусы учебного отправления").status_code == 404


def test_unknown_or_empty_title_and_no_user(client):
    assert get(client, "Нет такого документа").status_code == 404
    assert get(client, "   ").status_code == 404
    assert client.get("/documents", query_string={"title": "Глоссарий стажировки"}).status_code == 401
