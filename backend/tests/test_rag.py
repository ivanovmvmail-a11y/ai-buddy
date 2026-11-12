"""Офлайн-проверки загрузки, поиска и изоляции команд, без PostgreSQL/ключей."""
import math
import asyncio
from dataclasses import replace
from unittest.mock import Mock

import pytest

from app import async_runner, rag
from app.agent.users import DEMO_USERS
from app.config import settings
from app.rag.chunking import chunk_markdown
from app.rag.embeddings import DIMENSION, DeterministicEmbedder
from app.rag.ingest import DEMO_DOCS, ingest_directory, main, read_document
from app.rag.service import RAGService
from app.rag.storage import Document, InMemoryDocumentStore, SearchHit

run = async_runner.run


@pytest.fixture
def service():
    return RAGService(DeterministicEmbedder(), InMemoryDocumentStore())


@pytest.fixture
def demo(service):
    assert run(ingest_directory(service)) == (20, 20)
    return service


def test_embedding_is_deterministic_and_normalized():
    texts = ["Учебная доставка", "Учебная доставка", "Код ревью", "", "!!!", "ДОСТАВКА"]
    vectors = run(DeterministicEmbedder().embed(texts))
    assert vectors == run(DeterministicEmbedder().embed(texts))
    assert vectors[0] == vectors[1] and vectors[0] != vectors[2]
    assert vectors[-1] == run(DeterministicEmbedder().embed(["доставка"]))[0]
    for vector in vectors:
        assert len(vector) == DIMENSION
        assert all(math.isfinite(value) for value in vector)
        assert sum(value * value for value in vector) == pytest.approx(1)
    assert run(DeterministicEmbedder().embed([])) == []


def test_delivery_intern_never_sees_platform_documents(demo):
    """Точный запрос по чужому документу не даёт доступа даже при большом k."""
    for query in ("Лиловый конструктор", "Бумажный каталог", "Картонный дирижабль"):
        hits = run(demo.retrieve(query, DEMO_USERS["intern-ivan"], k=100))
        assert len(hits) == 14  # 8 общих + 6 своей команды
        assert all("Платформа объявлений" not in hit["title"] for hit in hits)
        assert all(query not in hit["content"] for hit in hits)
        assert any("Авито Доставка" in hit["title"] for hit in hits)
        assert any(hit["title"] == "Первые дни стажёра" for hit in hits)


@pytest.mark.parametrize("user_id", DEMO_USERS)
def test_all_roles_are_scoped_to_their_team(demo, user_id):
    user = DEMO_USERS[user_id]
    hits = run(demo.retrieve("учебный документ", user, k=100))
    expected = {
        document.title for document, _ in demo.store.documents.values()
        if document.team is None or document.team == user.team
    }
    assert {hit["title"] for hit in hits} == expected
    assert len(hits) == len(expected)


def test_filter_before_top_k(service):
    for index in range(6):
        run(service.ingest(Document(str(index), "Чужой", "точное совпадение", "Платформа объявлений")))
    run(service.ingest(Document("public", "Общий", "другие слова")))
    run(service.ingest(Document("own", "Свой", "ещё текст", "Авито Доставка")))
    hits = run(service.retrieve("точное совпадение", DEMO_USERS["intern-ivan"], k=2))
    assert {hit["title"] for hit in hits} == {"Общий", "Свой"}


def test_ingest_chunks_and_contract(service, monkeypatch):
    content = "# Заголовок\n\n" + ("Учебный markdown с вопросами.\n\n" * 40)
    document = Document("source", "Заголовок", content, url="https://example.invalid/source")
    count = run(service.ingest(document, max_chars=180, overlap=20))
    saved, chunks = service.store.documents["source"]
    assert saved == document and saved.content == content
    assert count == len(chunks) > 1
    assert all(0 < len(chunk.content) <= 180 for chunk in chunks)
    assert all(len(chunk.embedding) == 1024 for chunk in chunks)
    monkeypatch.setattr(rag, "get_service", lambda: service)
    hits = run(rag.retrieve("вопросами", DEMO_USERS["intern-anya"]))
    assert len(hits) == 4
    assert all(set(hit) == {"title", "content", "url"} for hit in hits)
    assert all(hit["title"] == document.title and hit["url"] == document.url for hit in hits)
    assert {hit["content"] for hit in hits} <= {chunk.content for chunk in chunks}


def test_reingest_replaces_chunks_and_team(service):
    old = Document("stable", "Старый", "старое содержимое " * 50, "Авито Доставка")
    run(service.ingest(old, max_chars=100, overlap=10))
    assert len(service.store.documents["stable"][1]) > 1
    new = replace(old, title="Новый", content="новый текст", team="Платформа объявлений", url=None)
    run(service.ingest(new))
    assert len(service.store.documents) == 1
    assert len(service.store.documents["stable"][1]) == 1
    assert run(service.retrieve("старое", DEMO_USERS["intern-ivan"])) == []
    assert run(service.retrieve("новый", DEMO_USERS["intern-anya"])) == [
        {"title": "Новый", "content": "новый текст", "url": None}
    ]


@pytest.mark.parametrize("vectors", [[], [[1.0]], [[float("nan")] * 1024],
                                    [[float("inf")] * 1024], [[0.0] * 1024]])
def test_bad_embeddings_do_not_replace_document(service, vectors):
    document = Document("stable", "Исходный", "старый текст")
    run(service.ingest(document))
    saved = service.store.documents["stable"]

    class BrokenEmbedder:
        dimension = 1024

        async def embed(self, texts):
            return vectors

    service.embedder = BrokenEmbedder()
    with pytest.raises(ValueError):
        run(service.ingest(replace(document, content="новый текст")))
    assert service.store.documents["stable"] == saved
    with pytest.raises(ValueError):
        run(service.retrieve("запрос", DEMO_USERS["intern-anya"]))


def test_wrong_embedder_dimension(service):
    class WrongDimension:
        dimension = 1536

    with pytest.raises(ValueError, match="1024"):
        RAGService(WrongDimension(), service.store)


@pytest.mark.parametrize("changes", [{"source_id": " "}, {"title": " "}, {"team": " "}, {"content": "\n "}])
def test_invalid_document_is_rejected(service, changes):
    with pytest.raises(ValueError):
        run(service.ingest(replace(Document("source", "Title", "text"), **changes)))
    assert service.store.documents == {}


@pytest.mark.parametrize("query,k", [("", 4), (" \n ", 4), ("query", 0), ("query", -2)])
def test_empty_inputs_skip_dependencies(service, monkeypatch, query, k):
    class NeverEmbed:
        async def embed(self, texts):
            pytest.fail("Empty requests must not embed text")

    service.embedder = NeverEmbed()
    monkeypatch.setattr(rag, "get_service", lambda: service)
    assert run(rag.retrieve(query, DEMO_USERS["intern-anya"], k)) == []
    assert run(service.retrieve(query, DEMO_USERS["intern-anya"], k)) == []


def test_unconfigured_database(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    assert rag.get_service() is None
    assert run(rag.retrieve("запрос", DEMO_USERS["intern-anya"])) == []
    monkeypatch.setattr(settings, "database_url", "postgresql://example.invalid/demo")
    rag.get_service.cache_clear()
    configured = rag.get_service()
    assert configured.store.database_url == settings.database_url
    assert isinstance(configured.embedder, DeterministicEmbedder)


def test_gigachat_embedder_selected(monkeypatch):
    from app.llm.embeddings import GigaChatEmbedder

    monkeypatch.setattr(settings, "embeddings_provider", "gigachat")
    monkeypatch.setattr(settings, "gigachat_credentials", "dGVzdDp0ZXN0")  # фиктивный тестовый ключ
    assert isinstance(rag.make_embedder(), GigaChatEmbedder)
    monkeypatch.setattr(settings, "embeddings_provider", "fake")
    assert isinstance(rag.make_embedder(), DeterministicEmbedder)


def test_service_is_cached_for_all_requests(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "postgresql://example.invalid/demo")
    store_factory = Mock(return_value=InMemoryDocumentStore())
    monkeypatch.setattr(rag, "PostgresDocumentStore", store_factory)
    first = rag.get_service()
    assert rag.get_service() is first
    for user_id in ("intern-ivan", "intern-anya"):
        assert run(rag.retrieve("query", DEMO_USERS[user_id])) == []
    assert rag.get_service().embedder is first.embedder
    store_factory.assert_called_once_with(settings.database_url)


@pytest.mark.parametrize("stage", ["factory", "embedder", "storage"])
def test_retrieval_failure_logs_and_chat_still_answers(client, service, monkeypatch, caplog, stage):
    def failed_factory():
        raise RuntimeError("factory unavailable")

    async def failed(*args):
        raise RuntimeError(f"{stage} unavailable")

    monkeypatch.setattr(rag, "get_service", failed_factory if stage == "factory" else lambda: service)
    if stage == "embedder":
        monkeypatch.setattr(service.embedder, "embed", failed)
    elif stage == "storage":
        monkeypatch.setattr(service.store, "search", failed)
    assert run(rag.retrieve("question", DEMO_USERS["intern-ivan"])) == []
    response = client.post("/chat", json={"messages": [{"role": "user", "content": "question"}]},
                           headers={"X-User-Id": "intern-anya"})
    assert response.status_code == 200
    body = response.get_json()
    assert "question" in body["reply"] and body["sources"] == []
    assert "unavailable" not in str(body)
    records = [record for record in caplog.records if record.name == "ai_buddy.rag"]
    assert records and all(record.exc_info for record in records)
    assert f"{stage} unavailable" in caplog.text


def test_empty_store_and_cosine_ranking(service):
    user = DEMO_USERS["intern-anya"]
    assert run(service.retrieve("код ревью", user)) == []
    run(service.ingest(Document("a", "Доставка", "посылка маршрут")))
    run(service.ingest(Document("b", "Ревью", "код ревью")))
    assert run(service.retrieve("код ревью", user, 1))[0]["title"] == "Ревью"


def test_dependency_failure_propagates(service, monkeypatch):
    async def failed(*args):
        raise RuntimeError("unavailable")

    monkeypatch.setattr(service.embedder, "embed", failed)
    with pytest.raises(RuntimeError, match="unavailable"):
        run(service.retrieve("запрос", DEMO_USERS["intern-anya"]))
    service.embedder = DeterministicEmbedder()
    monkeypatch.setattr(service.store, "search", failed)
    with pytest.raises(RuntimeError, match="unavailable"):
        run(service.retrieve("запрос", DEMO_USERS["intern-anya"]))


def test_service_rechecks_adapter_acl(service, monkeypatch):
    async def faulty_search(*args):
        return [SearchHit("Чужой", "скрытый текст", "https://example.invalid/private", "Авито Доставка"),
                SearchHit("Общий", "открытый текст", None, None)]

    monkeypatch.setattr(service.store, "search", faulty_search)
    assert run(service.retrieve("query", DEMO_USERS["intern-anya"])) == [
        {"title": "Общий", "content": "открытый текст", "url": None}
    ]


@pytest.mark.parametrize("text", ["", " \n ", "".join(chr(0x4E00 + index) for index in range(600)),
    "\n\n".join(f"абзац {index:04d}" for index in range(80)),
    "\n".join(f"строка {index:04d}" for index in range(100)),
    " ".join(f"слово{index:04d}" for index in range(150))])
def test_chunk_boundaries(text):
    chunks = chunk_markdown(text, max_chars=80, overlap=8)
    assert all(0 < len(chunk) <= 80 for chunk in chunks)
    assert bool(chunks) == bool(text.strip())
    if text.strip():
        assert chunks[0].startswith(text.strip()[:5])
        assert chunks[-1].endswith(text.strip()[-5:])
        # Каждая позиция исходного непустого текста покрыта хотя бы одним фрагментом.
        covered = [False] * len(text.strip())
        position = 0
        for chunk in chunks:
            start = text.strip().index(chunk, position)
            covered[start:start + len(chunk)] = [True] * len(chunk)
            position = start + 1
        assert all(flag or char.isspace() for flag, char in zip(covered, text.strip(), strict=True))


def test_zero_overlap_and_invalid_chunk_settings():
    assert chunk_markdown("a" * 35, max_chars=10, overlap=0) == ["a" * 10, "a" * 10, "a" * 10, "a" * 5]
    for size, overlap in ((0, 0), (-1, 0), (10, -1), (10, 10)):
        with pytest.raises(ValueError):
            chunk_markdown("text", size, overlap)


@pytest.mark.parametrize("separator", [" ", "\n", "\t"])
@pytest.mark.parametrize("overlap", [0, 3, 7, 18])
def test_overlap_starts_on_word_boundary(separator, overlap):
    words = [f"word{index:03d}suffix" for index in range(30)]
    text = separator.join(words)
    chunks = chunk_markdown(text, max_chars=55, overlap=overlap)
    assert len(chunks) > 1
    assert all(chunk.split()[0] in words for chunk in chunks)
    assert all(len(chunk) <= 55 for chunk in chunks)
    assert set(words) == {word for chunk in chunks for word in chunk.split()}


def test_demo_metadata_and_repeat_load(demo):
    documents = [read_document(path, path.name) for path in sorted(DEMO_DOCS.glob("*.md"))]
    assert len(documents) == 20
    assert sum(document.team is None for document in documents) == 8
    assert sum(document.team == "Авито Доставка" for document in documents) == 6
    assert sum(document.team == "Платформа объявлений" for document in documents) == 6
    assert all(not document.content.startswith("---") for document in documents)
    assert run(ingest_directory(demo)) == (20, 20)
    assert len(demo.store.documents) == 20


@pytest.mark.parametrize("text", ["# Missing metadata", "---\ntitle: t", "---\ntitle: t\n---\nbody",
    "---\nteam: null\n---\nbody", "---\ntitle: t\nteem: null\n---\nbody",
    "---\ntitle: t\nteam: null\nteam: Авито Доставка\n---\nbody",
    "---\ntitle: t\nteam:\n---\nbody", "---\ntitle: t\nteam: null\n---\n ",
    "---\ntitle: t\nteam: null\nbroken line\n---\nbody"])
def test_bad_metadata_fails_closed(tmp_path, text):
    path = tmp_path / "bad.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        read_document(path, "bad")


def test_all_metadata_checked_before_writing(service, tmp_path):
    (tmp_path / "a.md").write_text("---\ntitle: valid\nteam: null\n---\ntext", encoding="utf-8")
    (tmp_path / "z.md").write_text("---\ntitle: invalid\n---\ntext", encoding="utf-8")
    with pytest.raises(ValueError):
        run(ingest_directory(service, tmp_path))
    assert service.store.documents == {}


def test_windows_bom_markdown_loads_with_other_files(service, tmp_path):
    text = "---\ntitle: Учебный документ\nteam: Авито Доставка\n---\n# Текст\nПример"
    (tmp_path / "windows.md").write_text(text, encoding="utf-8-sig", newline="\r\n")
    (tmp_path / "unix.md").write_text(text, encoding="utf-8")
    assert run(ingest_directory(service, tmp_path)) == (2, 2)
    for document, chunks in service.store.documents.values():
        assert document.team == "Авито Доставка"
        assert document.content == "# Текст\nПример"
        assert "\ufeff" not in chunks[0].content


def test_empty_directory(service, tmp_path):
    with pytest.raises(ValueError, match="no markdown"):
        run(ingest_directory(service, tmp_path))


def test_cli_without_database(capsys):
    with pytest.raises(SystemExit) as error:
        main([])
    assert error.value.code == 2
    assert "DATABASE_URL" in capsys.readouterr().err


def test_cli_uses_shared_async_runner(service, monkeypatch, capsys):
    monkeypatch.setattr("app.rag.ingest.get_service", lambda: service)
    main(["--directory", str(DEMO_DOCS)])
    assert "Loaded 20 documents, 20 chunks" in capsys.readouterr().out


@pytest.mark.parametrize("stage", ["success", "metadata", "embedder", "storage"])
def test_cli_closes_store_on_same_loop_after_success_or_failure(service, monkeypatch, capsys, tmp_path, stage):
    closed, embedded = [], []
    original_embed = service.embedder.embed
    async def embed(texts):
        embedded.append(asyncio.get_running_loop())
        if stage == "embedder":
            raise RuntimeError("embedding failed")
        return await original_embed(texts)
    async def close():
        closed.append(asyncio.get_running_loop())
    async def failed_storage(*args):
        raise RuntimeError("storage failed")
    monkeypatch.setattr(service.embedder, "embed", embed)
    monkeypatch.setattr(service.store, "close", close)
    monkeypatch.setattr("app.rag.ingest.get_service", lambda: service)
    directory = DEMO_DOCS
    if stage == "metadata":
        (tmp_path / "invalid.md").write_text("no metadata", encoding="utf-8")
        directory = tmp_path
    if stage == "storage":
        monkeypatch.setattr(service.store, "upsert", failed_storage)
    if stage == "success":
        main(["--directory", str(directory)])
        assert "Loaded 20 documents" in capsys.readouterr().out
    else:
        with pytest.raises(ValueError if stage == "metadata" else RuntimeError):
            main(["--directory", str(directory)])
        assert "Loaded" not in capsys.readouterr().out
    async def loop():
        return asyncio.get_running_loop()
    assert closed == [run(loop())]
    assert all(item is closed[0] for item in embedded)


@pytest.mark.parametrize("user_id", DEMO_USERS)
def test_howto_queries_never_return_another_team_even_with_exact_foreign_text(demo, user_id):
    user = DEMO_USERS[user_id]
    documents = [document for document, _ in demo.store.documents.values()]
    allowed = {document.title for document in documents if document.team in (None, user.team)}
    howto_names = {
        "11-git-workflow.md", "12-red-pipeline.md", "13-team-space-access.md",
        "15-platform-local-run.md", "16-platform-reviewers.md", "17-platform-sandbox-setup.md",
        "18-delivery-local-run.md", "19-delivery-reviewers.md", "20-delivery-sandbox-setup.md",
    }
    new_documents = [document for document in documents
                     if document.source_id.removeprefix("demo:") in howto_names]
    assert {document.source_id.removeprefix("demo:") for document in new_documents} == howto_names
    for document in new_documents:
        hits = run(demo.retrieve(document.content, user, k=100))
        assert {hit["title"] for hit in hits} == allowed
        if document.team is not None and document.team != user.team:
            top = run(demo.retrieve(document.content, user, k=1))
            assert top and top[0]["title"] in allowed
            assert document.title not in {hit["title"] for hit in top}
