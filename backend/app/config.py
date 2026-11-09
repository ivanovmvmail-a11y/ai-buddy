"""Настройки приложения. Значения берутся из переменных окружения / файла backend/.env."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # gigachat | openai | echo  (echo — заглушка без ключей, для разработки)
    llm_provider: str = "echo"

    # GigaChat (https://developers.sber.ru/studio)
    gigachat_credentials: str = ""  # Authorization Key из личного кабинета
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_model: str = "GigaChat-2"
    gigachat_ca_bundle_file: str = ""  # путь к russian_trusted_root_ca.cer (см. README)
    gigachat_verify_ssl: bool = True

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

    # CORS: адреса фронтенда через запятую
    frontend_origins: str = "http://localhost:3000"


settings = Settings()
