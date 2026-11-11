"""Объяснение пункта без модели: раздел документа пункта, глубина по уровню, «по шагам», «к кому идти» (аудит S1, S7)."""
import pytest
from .conftest import as_user

from app.agent.explain import DEMO_DOCS_URL, load_doc


def item_id(client, title, user="intern-anya"):
    items = client.get("/plan", headers=as_user(user)).get_json()["items"]
    return next(i["id"] for i in items if i["title"] == title)


def explain(client, item, kind="explain", user="intern-anya", intern_id=None):
    url = f"/plan/items/{item}/explained" + (f"?intern_id={intern_id}" if intern_id else "")
    return client.post(url, json={"kind": kind}, headers=as_user(user))


def test_explanation_comes_from_item_document_with_working_link(client):
    res = explain(client, item_id(client, "Познакомиться с командой"))
    assert res.status_code == 201
    body = res.get_json()
    assert body["answer_id"].startswith("ans_")
    assert "Познакомься с наставником и уточни цель стажировки" in body["text"]  # текст раздела, не шаблон
    assert body["source"] == {"title": "Первые дни стажёра", "url": DEMO_DOCS_URL + "01-onboarding.md"}
    assert body["chips"] == ["Как это сделать по шагам?", "К кому идти, если не получается?"]


def test_depth_follows_skill_level(client):
    novice = explain(client, item_id(client, "Открыть пространство Платформы объявлений")).get_json()["text"]
    confident = explain(client, item_id(client, "Разобрать документы Платформы объявлений")).get_json()["text"]
    assert "Разберём подробно" in novice and "коротко" not in novice
    assert "Ты в этой теме уверенно, поэтому коротко" in confident
    assert "слаб" not in novice + confident and "только начинается" not in novice


def test_steps_are_numbered_sentences_of_the_document(client):
    body = explain(client, item_id(client, "Запустить песочницу объявлений"), "steps").get_json()
    lines = body["text"].splitlines()
    assert lines[0].startswith("По шагам — по разделу")
    assert lines[1].startswith("1. ") and lines[2].startswith("2. ")
    assert "Проверь себя на практике: Создай карточку бумажного змея" in body["text"]
    assert body["chips"] == ["К кому идти, если не получается?"]


def test_steps_without_document_do_not_invent(client):
    text = explain(client, item_id(client, "Завести конспект встреч с наставником"), "steps").get_json()["text"]
    assert "в документах нет — выдумывать не буду" in text and "Пётр Волков" in text


@pytest.mark.parametrize(("user", "title", "mentor"), [
    ("intern-anya", "Запросить базовые доступы", "Пётр Волков"),
    ("intern-ivan", "Запросить базовые доступы", "Мария Орлова"),
])
def test_who_names_own_mentor_and_route_from_document(client, user, title, mentor):
    body = explain(client, item_id(client, title, user), "who", user).get_json()
    assert f"твой наставник, {mentor}" in body["text"]
    assert "Если не хватает доступа" in body["text"]  # раздел «Технические вопросы» документа «К кому идти»
    assert body["source"]["title"] == "К кому идти с вопросом"


def test_item_of_other_person_names_who_does_it(client):
    text = explain(client, item_id(client, "Назначить регулярные встречи 1:1")).get_json()["text"]
    assert "отмечает наставник — Пётр Волков" in text
    lead = explain(client, item_id(client, "Обсудить цели и ожидаемый результат"), "who").get_json()["text"]
    assert "ведёт руководитель — Ольга Новикова" in lead


def test_mentor_explains_own_intern_item_but_not_foreign(client):
    anya_item = item_id(client, "Познакомиться с командой")
    assert explain(client, anya_item, user="mentor-petr", intern_id="intern-anya").status_code == 201
    assert explain(client, anya_item, user="mentor-maria", intern_id="intern-anya").status_code == 404
    assert explain(client, anya_item, user="intern-ivan").status_code == 404  # чужой пункт не отличить от отсутствующего


def test_unknown_kind_is_rejected(client):
    assert explain(client, item_id(client, "Познакомиться с командой"), "poem").status_code == 422


def test_explanation_counts_in_metrics(client):
    explain(client, item_id(client, "Познакомиться с командой"))
    metrics = client.get("/metrics?intern_id=intern-anya", headers=as_user("mentor-petr")).get_json()
    assert metrics["questions"] >= 1 and metrics["with_source_share"] > 0


@pytest.mark.parametrize("source_id", [None, "kb:42", "demo:../../config.py", "demo:нет-такого.md"])
def test_load_doc_only_reads_demo_documents(source_id):
    assert load_doc(source_id) is None
