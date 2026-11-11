"""CLI: uv run python -m app.rag.ingest — загрузить синтетические демо-документы."""
import argparse
from pathlib import Path

from app.async_runner import run

from . import get_service
from .service import RAGService
from .storage import Document

DEMO_DOCS = Path(__file__).parent / "demo_docs"


def read_document(path: Path, source_id: str) -> Document:
    """Небольшое строгое подмножество front matter: однострочные title/team/url.

    team обязателен: только явное `team: null` делает документ общим.
    Неизвестные/повторные поля запрещены, чтобы опечатка не расширила доступ.
    """
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise ValueError(f"{path.name}: metadata block is required")
    end = lines.index("---", 1)
    metadata = {}
    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if not separator or key not in {"title", "team", "url"} or key in metadata or not value:
            raise ValueError(f"{path.name}: invalid or duplicate metadata field")
        metadata[key] = value
    if not metadata.get("title") or "team" not in metadata:
        raise ValueError(f"{path.name}: title and explicit team are required")
    content = "\n".join(lines[end + 1:]).strip()
    if not content:
        raise ValueError(f"{path.name}: document is empty")
    return Document(
        source_id=source_id, title=metadata["title"], content=content,
        team=None if metadata["team"] == "null" else metadata["team"],
        url=None if metadata.get("url") in {None, "null"} else metadata["url"],
    )


async def ingest_directory(service: RAGService, directory: Path = DEMO_DOCS) -> tuple[int, int]:
    paths = sorted(directory.glob("*.md"))
    if not paths:
        raise ValueError("Directory contains no markdown documents")
    # Проверяем все метаданные до первой записи в БД.
    documents = [read_document(path, source_id=f"demo:{path.name}") for path in paths]
    chunks = 0
    for document in documents:
        chunks += await service.ingest(document)
    return len(documents), chunks


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Load synthetic RAG demo documents using DATABASE_URL")
    parser.add_argument("--directory", type=Path, default=DEMO_DOCS)
    args = parser.parse_args(argv)
    service = get_service()
    if service is None:
        parser.error("Set DATABASE_URL before loading documents")
    async def ingest_and_close():
        try:
            return await ingest_directory(service, args.directory)
        finally:
            await service.store.close()

    documents, chunks = run(ingest_and_close())
    print(f"Loaded {documents} documents, {chunks} chunks (embedder: {type(service.embedder).__name__})")


if __name__ == "__main__":
    main()
