"""Загрузка и retrieval не зависят от конкретного эмбеддера или транспорта БД."""
from app.agent.users import User

from .chunking import chunk_markdown
from .embeddings import DIMENSION, Embedder, validate_embedding
from .storage import Chunk, Document, DocumentStore


class RAGService:
    def __init__(self, embedder: Embedder, store: DocumentStore) -> None:
        if embedder.dimension != DIMENSION:
            raise ValueError(f"Embedder dimension must be {DIMENSION}")
        self.embedder = embedder
        self.store = store

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        vectors = await self.embedder.embed(texts)
        if len(vectors) != len(texts):
            raise ValueError("Embedder returned an unexpected number of vectors")
        for vector in vectors:
            validate_embedding(vector)
        return vectors

    async def ingest(self, document: Document, *, max_chars: int = 1200, overlap: int = 150) -> int:
        if not document.source_id.strip() or not document.title.strip():
            raise ValueError("Document source_id and title must not be empty")
        if document.team is not None and not document.team.strip():
            raise ValueError("Use team=None for a shared document, not an empty team")
        texts = chunk_markdown(document.content, max_chars, overlap)
        if not texts:
            raise ValueError("Document content must not be empty")
        # Считаем/проверяем ВСЕ векторы до записи, чтобы не потерять старую версию при ошибке.
        vectors = await self._embed(texts)
        await self.store.upsert(document, [Chunk(text, vector) for text, vector in zip(texts, vectors, strict=True)])
        return len(texts)

    async def retrieve(self, query: str, user: User, k: int = 4) -> list[dict]:
        if not query.strip() or k <= 0:
            return []
        [embedding] = await self._embed([query])
        hits = await self.store.search(embedding, user.team, k)
        # Дополнительная проверка результата адаптера: чужой текст не покидает RAG.
        return [
            {"title": hit.title, "content": hit.content, "url": hit.url}
            for hit in hits if hit.team is None or hit.team == user.team
        ][:k]
