"""RAG (зона Codex): загрузка документов команды, эмбеддинги, поиск в Supabase (pgvector).

Контракт, на который опирается агент (не менять без PR [API]):
    async def retrieve(query: str, k: int = 4) -> list[dict]
    каждый dict: {"title": str, "content": str, "url": str | None}
"""


async def retrieve(query: str, k: int = 4) -> list[dict]:
    # TODO(codex): реализовать поиск по векторной базе
    return []
