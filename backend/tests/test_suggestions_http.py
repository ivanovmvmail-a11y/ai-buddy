"""SPEC 4, 5 (11.11): HTTP предложений по уровню, «это я уже знаю» и сравнения планов поверх hiring/checklist."""
import pytest
from .conftest import as_user


def get(client, url, user):
    return client.get(url, headers=as_user(user))


def post(client, url, body, user):
    return client.post(url, json=body, headers=as_user(user))


def personal(client, user="intern-anya", intern=None):
    url = f"/plan?intern_id={intern}" if intern else "/plan"
    return [i for i in get(client, url, user).get_json()["items"] if i["kind"] == "personal"]


def git_item(client):
    return next(i for i in personal(client) if i["topic"] == "git")


def test_known_creates_suggestion_only_mentor_sees(client):
    item = git_item(client)
    res = post(client, f"/plan/items/{item['id']}/known", {"known": True}, "intern-anya")
    assert res.status_code == 200
    body = res.get_json()
    assert body["known_marked"] is True and body["status"] != "done"  # пункт не закрывается

    [sug] = get(client, "/skills/suggestions", "mentor-petr").get_json()["suggestions"]
    assert sug["intern_name"] == "Аня Смирнова" and sug["topic"] == "git"
    assert (sug["from_level"], sug["to_level"]) == ("novice", "familiar")
    assert "это я уже знаю" in sug["basis"] and "evidence" not in sug
    for user in ("intern-anya", "lead-olga", "curator-dmitry", "hrbp-elena"):
        assert get(client, "/skills/suggestions", user).status_code == 404
    assert get(client, "/skills/suggestions", "mentor-maria").get_json() == {"suggestions": []}


def test_accept_raises_level_and_rebuilds_plan(client):
    item = git_item(client)
    post(client, f"/plan/items/{item['id']}/known", {"known": True}, "intern-anya")
    [sug] = get(client, "/skills/suggestions", "mentor-petr").get_json()["suggestions"]
    assert post(client, f"/skills/suggestions/{sug['id']}/decide", {"accept": True}, "mentor-maria").status_code == 404
    res = post(client, f"/skills/suggestions/{sug['id']}/decide", {"accept": True}, "mentor-petr")
    assert res.status_code == 200 and res.get_json()["status"] == "accepted"
    assert get(client, "/profile/skills", "intern-anya").get_json()["skills"]["git"] == "familiar"
    assert item["id"] not in {i["id"] for i in personal(client)}  # незакрытый персональный пункт снят
    assert get(client, "/skills/suggestions", "mentor-petr").get_json() == {"suggestions": []}
    assert post(client, f"/skills/suggestions/{sug['id']}/decide", {"accept": False}, "mentor-petr").status_code == 409


def test_dismiss_keeps_level(client):
    post(client, f"/plan/items/{git_item(client)['id']}/known", {"known": True}, "intern-anya")
    [sug] = get(client, "/skills/suggestions", "mentor-petr").get_json()["suggestions"]
    assert post(client, f"/skills/suggestions/{sug['id']}/decide", {"accept": "yes"}, "mentor-petr").status_code == 422
    res = post(client, f"/skills/suggestions/{sug['id']}/decide", {"accept": False}, "mentor-petr")
    assert res.get_json()["status"] == "dismissed"
    assert get(client, "/profile/skills", "intern-anya").get_json()["skills"]["git"] == "novice"
    history = get(client, "/skills/suggestions?status=", "mentor-petr").get_json()["suggestions"]
    assert [s["status"] for s in history] == ["dismissed"]


def test_known_rules(client):
    item = git_item(client)
    assert post(client, f"/plan/items/{item['id']}/known", {"known": True}, "intern-ivan").status_code == 404
    assert post(client, f"/plan/items/{item['id']}/known", {"known": True}, "mentor-petr").status_code == 404
    assert post(client, f"/plan/items/{item['id']}/known", {"known": 1}, "intern-anya").status_code == 422
    no_topic = next(i for i in get(client, "/plan", "intern-anya").get_json()["items"]
                    if not i["topic"] and i["owner_role"] == "intern")
    assert post(client, f"/plan/items/{no_topic['id']}/known", {"known": True}, "intern-anya").status_code == 422
    res = post(client, f"/plan/items/{item['id']}/known", {"known": False}, "intern-anya")
    assert res.status_code == 200 and res.get_json()["known_marked"] is False


def test_compare_two_own_interns(client):
    body = get(client, "/plan/compare?intern_ids=intern-anya,intern-kirill", "mentor-petr").get_json()
    assert [i["name"] for i in body["interns"]] == ["Аня Смирнова", "Кирилл Егоров"]
    assert body["common"] and all(set(c["by_intern"]) == {"intern-anya", "intern-kirill"} for c in body["common"])
    anya = {i["topic"] for i in body["personal"]["intern-anya"]}
    kirill = {i["topic"] for i in body["personal"]["intern-kirill"]}
    assert "git" in anya and "git" not in kirill and "sql" in kirill
    assert all(i["reason"] for i in body["personal"]["intern-anya"] + body["personal"]["intern-kirill"])


@pytest.mark.parametrize("user,ids,code", [
    ("mentor-maria", "intern-anya,intern-kirill", 404),
    ("mentor-petr", "intern-anya,intern-ivan", 404),
    ("intern-anya", "intern-anya,intern-kirill", 404),
    ("lead-olga", "intern-anya,intern-kirill", 404),
    ("mentor-petr", "intern-anya", 422),
    ("mentor-petr", "intern-anya,intern-anya", 422),
])
def test_compare_rights(client, user, ids, code):
    assert get(client, f"/plan/compare?intern_ids={ids}", user).status_code == code


def test_new_interns_have_plans_and_mentors_see_two(client):
    assert {i["id"] for i in get(client, "/interns", "mentor-petr").get_json()["interns"]} == {"intern-anya", "intern-kirill"}
    assert {i["id"] for i in get(client, "/interns", "mentor-maria").get_json()["interns"]} == {"intern-ivan", "intern-liza"}
    for intern in ("intern-kirill", "intern-liza"):
        assert get(client, "/plan", intern).status_code == 200


# --- Правка персональных пунктов наставником (SPEC 3.1, 5; сервис — checklist.add/remove_personal_item) ----

def test_catalog_only_for_own_mentor(client):
    items = get(client, "/plan/catalog?intern_id=intern-anya", "mentor-petr").get_json()["items"]
    assert items and all(c["team"] == "Платформа объявлений" for c in items)
    assert any(c["topic"] == "git" and c["in_plan"] for c in items)
    for user in ("intern-anya", "mentor-maria", "lead-olga", "curator-dmitry"):
        assert get(client, "/plan/catalog?intern_id=intern-anya", user).status_code == 404
    assert get(client, "/plan/catalog", "mentor-petr").status_code == 404


def test_mentor_adds_and_removes_personal_item(client):
    catalog = get(client, "/plan/catalog?intern_id=intern-anya", "mentor-petr").get_json()["items"]
    free = next(c for c in catalog if not c["in_plan"])
    res = post(client, "/plan/items", {"intern_id": "intern-anya", "catalog_key": free["key"]}, "mentor-petr")
    assert res.status_code == 201
    item = res.get_json()
    assert item["kind"] == "personal" and item["reason"] == "добавил наставник"
    assert item["id"] in {i["id"] for i in personal(client)}
    assert post(client, "/plan/items", {"intern_id": "intern-anya", "catalog_key": free["key"]},
                "mentor-petr").status_code == 409
    bell = get(client, "/reminders", "intern-anya").get_json()["reminders"]
    assert any(r["kind"] == "personal_item_added" for r in bell)

    assert client.delete(f"/plan/items/{item['id']}", headers=as_user("mentor-maria")).status_code == 404
    assert client.delete(f"/plan/items/{item['id']}", headers=as_user("intern-anya")).status_code == 404
    assert client.delete(f"/plan/items/{item['id']}", headers=as_user("mentor-petr")).status_code == 204
    assert item["id"] not in {i["id"] for i in personal(client)}
    assert client.delete(f"/plan/items/{item['id']}", headers=as_user("mentor-petr")).status_code == 404


def test_common_item_cannot_be_removed_and_foreign_key_hidden(client):
    common = next(i for i in get(client, "/plan", "intern-anya").get_json()["items"] if i["kind"] == "common")
    assert client.delete(f"/plan/items/{common['id']}", headers=as_user("mentor-petr")).status_code == 403
    foreign = next(c for c in get(client, "/plan/catalog?intern_id=intern-ivan", "mentor-maria").get_json()["items"])
    assert post(client, "/plan/items", {"intern_id": "intern-anya", "catalog_key": foreign["key"]},
                "mentor-petr").status_code == 404
