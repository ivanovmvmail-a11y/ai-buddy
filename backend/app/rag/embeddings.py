"""Контракт эмбеддера; настоящий GigaChat-адаптер подключается отдельно."""
import hashlib
import math
import re
from typing import Protocol

DIMENSION = 1024


class Embedder(Protocol):
    dimension: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def validate_embedding(vector: list[float]) -> None:
    if len(vector) != DIMENSION:
        raise ValueError(f"Embedding must have {DIMENSION} dimensions")
    if not all(math.isfinite(value) for value in vector) or not any(vector):
        raise ValueError("Embedding must be finite and nonzero")


class DeterministicEmbedder:
    """Поддельный bag-of-words для офлайн-тестов/демо, без семантической модели.

    SHA-256 вместо hash(): результат одинаков в разных процессах Python.
    """

    dimension = DIMENSION

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in re.findall(r"\w+", text.casefold()) or ["<empty>"]:
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                vector[int.from_bytes(digest[:4], "big") % self.dimension] += 1.0
            norm = math.sqrt(sum(value * value for value in vector))
            result.append([value / norm for value in vector])
        return result
