"""Настройки приложения. Значения берутся из переменных окружения / файла backend/.env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # gigachat | openai | echo  (echo — заглушка без ключей, для разработки)
    llm_provider: str = "scenario"
    # Случайность ответов модели: низкая — строже держит правило «нет в документах — так и скажи» и даёт
    # одинаковый ответ от прогона к прогону (прогон GigaChat 12.11). 0 у GigaChat не допускается.
    llm_temperature: float = 0.1

    # GigaChat (https://developers.sber.ru/studio)
    gigachat_credentials: str = ""  # Authorization Key из личного кабинета
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"
    gigachat_ca_bundle_file: str = ""  # путь к russian_trusted_root_ca.cer (см. README)
    gigachat_verify_ssl: bool = True

    # Эмбеддинги для поиска по документам: fake (по словам, без ключей) | gigachat.
    # gigachat нужен оплаченный пакет эмбеддингов: на бесплатном тарифе API отвечает 402.
    # Документы и запросы должны векториться ОДНИМ эмбеддером: после смены — перезагрузить документы.
    embeddings_provider: str = "fake"
    gigachat_embeddings_model: str = "Embeddings"  # 1024 измерения, как в схеме базы

    # Любой OpenAI-совместимый API (OpenRouter, YandexGPT OpenAI-endpoint и т.п.)
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = "gpt-4o-mini"

    # PostgreSQL + pgvector (зона Codex). В Docker задаётся в docker-compose.yml,
    # для облака — строка подключения Supabase (Project Settings → Database).
    database_url: str = ""

    # Supabase (зона Codex)
    supabase_url: str = ""
    supabase_service_key: str = ""

    # Журнал сервера: DEBUG | INFO | WARNING. INFO — видно права, черновики и вызовы инструментов (без текстов вопросов).
    log_level: str = "INFO"

    # Как агент чата ходит к корпоративным сервисам (app/agent/services.py):
    #   direct — вызовом функций в том же процессе (по умолчанию: тесты и запуск без MCP SDK);
    #   mcp    — MCP-клиентом по протоколу MCP к серверу app/mcp_server (в Docker включено, docker-compose.yml).
    agent_services: str = "direct"

    # Код-слово для демо-кнопок «Сброс» и «Следующий день» (заголовок X-Demo-Key).
    # Пусто — кнопки без пароля (локально и в Docker у эксперта). На публичном сайте — задать.
    demo_key: str = ""

    # CORS: адреса фронтенда через запятую
    frontend_origins: str = "http://localhost:3000"


settings = Settings()
