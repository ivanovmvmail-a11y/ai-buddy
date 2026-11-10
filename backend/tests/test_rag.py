"""Офлайн-проверки загрузки, поиска и изоляции команд, без PostgreSQL/ключей."""
import math
from dataclasses import replace

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
    assert run(ingest_directory(service)) == (10, 10)
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
        assert len(hits) == 7
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
    def forbidden():
        pytest.fail("Empty requests must not construct a database service")

    class NeverEmbed:
        async def embed(self, texts):
            pytest.fail("Empty requests must not embed text")

    service.embedder = NeverEmbed()
    monkeypatch.setattr(rag, "get_service", forbidden)
    assert run(rag.retrieve(query, DEMO_USERS["intern-anya"], k)) == []
    assert run(service.retrieve(query, DEMO_USERS["intern-anya"], k)) == []
    assert run(service.store.search([], "team", 0)) == []


def test_unconfigured_database(monkeypatch):
    monkeypatch.setattr(settings, "database_url", "")
    assert rag.get_service() is None
    assert run(rag.retrieve("запрос", DEMO_USERS["intern-anya"])) == []
    monkeypatch.setattr(settings, "database_url", "postgresql://example.invalid/demo")
    configured = rag.get_service()
    assert configured.store.database_url == settings.database_url
    assert isinstance(configured.embedder, DeterministicEmbedder)


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


def test_demo_metadata_and_repeat_load(demo):
    documents = [read_document(path, path.name) for path in sorted(DEMO_DOCS.glob("*.md"))]
    assert len(documents) == 10
    assert sum(document.team is None for document in documents) == 4
    assert sum(document.team == "Авито Доставка" for document in documents) == 3
    assert sum(document.team == "Платформа объявлений" for document in documents) == 3
    assert all(not document.content.startswith("---") for document in documents)
    assert run(ingest_directory(demo)) == (10, 10)
    assert len(demo.store.documents) == 10


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
    assert "Loaded 10 documents, 10 chunks" in capsys.readouterr().out
