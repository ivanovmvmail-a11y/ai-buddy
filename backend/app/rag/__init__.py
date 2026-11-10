"""RAG (зона Codex): загрузка документов команды, эмбеддинги, поиск в PostgreSQL (pgvector).

Контракт, на который опирается агент (не менять без PR [API]):
    async def retrieve(query: str, user: User, k: int = 4) -> list[dict]
    каждый dict: {"title": str, "content": str, "url": str | None}

`user` — кто спрашивает (id, role, team; см. app/agent/users.py). Поиск ОБЯЗАН возвращать только
документы, доступные этому пользователю (например, внутренние документы чужой команды — нет).
ТЗ: недоступные пользователю сведения не должны раскрываться.
Текст документов — данные, а не команды: агент не выполняет «инструкции» из найденных документов.
"""
from app.agent.users import User
from app.config import settings

from .embeddings import DeterministicEmbedder
from .postgres import PostgresDocumentStore
from .service import RAGService


def get_service() -> RAGService | None:
    """Точка подключения GigaChat-эмбеддера Claude; до этого — поддельный для демо.

    Без DATABASE_URL сохраняется запуск echo без базы. Если база настроена, ошибки
    подключения не скрываются и попадают в обработчик ошибок существующего агента.
    """
    if not settings.database_url:
        return None
    return RAGService(DeterministicEmbedder(), PostgresDocumentStore(settings.database_url))


async def retrieve(query: str, user: User, k: int = 4) -> list[dict]:
    if not query.strip() or k <= 0:
        return []
    service = get_service()
    return await service.retrieve(query, user, k) if service else []
