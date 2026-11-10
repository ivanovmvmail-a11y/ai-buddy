"""Эмбеддер GigaChat для поиска по документам (контракт — app/rag/embeddings.py: Embedder)."""
from app.config import settings

BATCH_SIZE = 16  # текстов в одном запросе к API


class GigaChatEmbedder:
    name = "gigachat"
    dimension = 1024  # модель Embeddings

    def __init__(self, client=None, model: str | None = None) -> None:
        if client is None:
            from .gigachat_provider import make_client

            client = make_client()
        self._client = client
        self._model = model or settings.gigachat_embeddings_model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), BATCH_SIZE):
            response = await self._client.aembeddings(texts[start:start + BATCH_SIZE], model=self._model)
            vectors.extend(item.embedding for item in sorted(response.data, key=lambda item: item.index))
        return vectors


def embeddings_provider() -> str:
    """gigachat — только если выбран явно (EMBEDDINGS_PROVIDER), иначе поддельный по словам."""
    return "gigachat" if settings.embeddings_provider.strip().lower() == "gigachat" else "fake"
