"""Хранилище за интерфейсом; in-memory реализация не требует базы и сети."""
import math
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Document:
    source_id: str
    title: str
    content: str
    team: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class Chunk:
    content: str
    embedding: list[float]


@dataclass(frozen=True)
class SearchHit:
    title: str
    content: str
    url: str | None
    team: str | None


class DocumentStore(Protocol):
    async def close(self) -> None:
        """Освободить ресурсы на event loop владельца хранилища."""
        ...

    async def delete(self, source_id: str) -> None:
        """Идемпотентно удалить документ и его фрагменты по внутреннему source_id."""
        ...

    async def upsert(self, document: Document, chunks: list[Chunk]) -> None:
        """Атомарно заменить документ и все его фрагменты по source_id."""
        ...

    async def search(self, embedding: list[float], team: str, k: int) -> list[SearchHit]:
        """Выбрать k ближайших доступных фрагментов; k > 0 проверяется сервисом."""
        ...


class InMemoryDocumentStore:
    def __init__(self, *, min_similarity: float | None = None) -> None:
        self.min_similarity = min_similarity
        self.documents: dict[str, tuple[Document, list[Chunk]]] = {}

    async def close(self) -> None:
        pass

    async def delete(self, source_id: str) -> None:
        self.documents.pop(source_id, None)

    async def upsert(self, document: Document, chunks: list[Chunk]) -> None:
        self.documents[document.source_id] = (document, chunks)

    async def search(self, embedding: list[float], team: str, k: int) -> list[SearchHit]:
        query_norm = math.sqrt(sum(value * value for value in embedding))
        ranked = []
        for source_id, (document, chunks) in self.documents.items():
            if document.team is not None and document.team != team:
                continue
            for index, chunk in enumerate(chunks):
                norm = math.sqrt(sum(value * value for value in chunk.embedding))
                similarity = sum(a * b for a, b in zip(embedding, chunk.embedding, strict=True))
                similarity /= query_norm * norm
                if self.min_similarity is not None and similarity < self.min_similarity:
                    continue
                ranked.append((-similarity, source_id, index, SearchHit(
                    title=document.title, content=chunk.content, url=document.url, team=document.team,
                )))
        ranked.sort(key=lambda item: item[:3])
        return [item[3] for item in ranked[:k]]
