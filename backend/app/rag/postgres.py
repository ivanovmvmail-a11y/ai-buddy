"""Прямое async-подключение psycopg; Supabase REST и специальные роли не нужны."""
from app.db.pool import PostgresPoolOwner

from .embeddings import validate_embedding
from .storage import Chunk, Document, SearchHit


def _vector_literal(embedding: list[float]) -> str:
    validate_embedding(embedding)
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


class PostgresDocumentStore(PostgresPoolOwner):
    async def delete(self, source_id: str) -> None:
        async with (await self._get_pool()).connection() as connection:
            await connection.execute("DELETE FROM public.rag_documents WHERE source_id=%s", (source_id,))

    async def upsert(self, document: Document, chunks: list[Chunk]) -> None:
        vectors = [_vector_literal(chunk.embedding) for chunk in chunks]
        async with (await self._get_pool()).connection() as connection:
            # Новая установка — extensions, существующая может оставаться в public.
            await connection.execute("SET LOCAL search_path = public, extensions")
            cursor = await connection.execute(
                """INSERT INTO public.rag_documents (source_id, title, url, content, team)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (source_id) DO UPDATE SET
                       title = EXCLUDED.title, url = EXCLUDED.url,
                       content = EXCLUDED.content, team = EXCLUDED.team
                   RETURNING id""",
                (document.source_id, document.title, document.url, document.content, document.team),
            )
            document_id = (await cursor.fetchone())["id"]
            await connection.execute("DELETE FROM public.rag_chunks WHERE document_id = %s", (document_id,))
            async with connection.cursor() as cursor:
                await cursor.executemany(
                    """INSERT INTO public.rag_chunks (document_id, chunk_index, content, embedding)
                       VALUES (%s, %s, %s, %s::vector)""",
                    [(document_id, index, chunk.content, vector)
                     for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))],
                )
        # Контекст коммитит/откатывает транзакцию и возвращает соединение в пул.

    async def search(self, embedding: list[float], team: str, k: int) -> list[SearchHit]:
        vector = _vector_literal(embedding)
        async with (await self._get_pool()).connection() as connection:
            await connection.execute("SET LOCAL search_path = public, extensions")
            # set_config(..., true) эквивалентен SET LOCAL, значение параметризовано.
            await connection.execute("SELECT set_config('app.rag_team', %s, true)", (team,))
            cursor = await connection.execute(
                """SELECT d.title, c.content, d.url, d.team
                   FROM public.rag_chunks AS c
                   JOIN public.rag_documents AS d ON d.id = c.document_id
                   WHERE d.team IS NULL OR d.team = %s
                   ORDER BY c.embedding <=> %s::vector, d.source_id, c.chunk_index
                   LIMIT %s""",
                (team, vector, k),
            )
            return [SearchHit(**row) for row in await cursor.fetchall()]
