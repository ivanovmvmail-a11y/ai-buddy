# Backend AI-buddy (Flask + gunicorn). Собирается из docker-compose.yml в корне.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала только зависимости — этот слой кешируется, пока не меняется uv.lock
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY certs ./certs
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    # без backend/.env работает демо-режим: LLM-заглушка, ключи не нужны
    LLM_PROVIDER=echo

RUN useradd --create-home --uid 10001 buddy
USER buddy

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)"

# 1 процесс (общий event loop для LLM-клиентов, см. app/async_runner.py) + потоки для параллельных запросов
# Seed онбординга заполняет только пустую базу. При ошибке хранилища запуск прерывается,
# чтобы не выдавать эксперту пустой план. RAG остаётся необязательным контекстом чата.
CMD ["sh", "-c", "python -m app.mcp_server.seed && (python -m app.rag.ingest || echo 'WARNING: demo documents were not loaded') && exec gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 8 --timeout 180 app.main:app"]
