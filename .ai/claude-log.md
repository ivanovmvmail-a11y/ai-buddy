# Журнал Claude

Формат записи (новые сверху):
```
## ГГГГ-ММ-ДД — <задача> (ветка)
- Сделано:
- Дальше:
- Вопросы/блокеры:
- Что важно знать Codex:
```

## 2026-11-10 — инструменты агента (claude/agent-tools) [API]
- Сделано: LLM-слой с вызовом инструментов (GigaChat functions, OpenAI tools; проверено вживую на GigaChat). Агент в цикле (до 5 шагов). Права проверяются перед каждым вызовом (роль + доступ к данным), недоступные инструменты модели не показываются. Write-инструменты → черновик → `POST /actions/{id}/confirm` (повторная проверка прав) → результат сохраняется. Роли-имитация: стажёр, наставник, руководитель, HR BP, куратор; пользователь по заголовку `X-User-Id`. Демо-инструменты: профиль, профиль стажёра, напоминание. Тесты: 41, покрытие backend 99%.
- Дальше: хранилище действий в PostgreSQL (сейчас в памяти); продуктовые инструменты после интервью; карточка черновика на фронте (после Q&A по фронтенду).
- Что важно знать Codex: HANDOFF от 2026-11-10 «инструменты агента».

## 2026-11-10 — Docker (claude/docker)
- Сделано: `docker-compose.yml` (db PostgreSQL+pgvector, backend на gunicorn, frontend Next.js standalone), Dockerfile для backend и frontend, демо-режим без ключей (echo), `DATABASE_URL` в конфиге, README «Запуск через Docker». Починил: `frontend/.env.example` не попадал в git.
- CI (с разрешения Миши): `.github/workflows/ci.yml` — backend-тесты + покрытие, frontend lint + build, docker compose up с проверкой /health, /chat, сайта и pgvector. Docker проверяется на GitHub, т.к. на ПК Миши выключен SVM в BIOS (нет проводной клавиатуры).
- Проверено: `uv sync --frozen --no-dev`, pytest (7 passed), `npm run build` со standalone. **Не проверено**: сам `docker compose up` — на компьютере Миши нет Docker Desktop.
- Дальше: проверить compose после установки Docker; инструменты агента (проверка прав перед каждым вызовом + черновик → подтверждение); шаблон SDD.
- Что важно знать Codex: см. HANDOFF от 2026-11-10 — база через `DATABASE_URL`, миграции должны работать на чистом PostgreSQL.

## 2026-11-09 — переход backend на Flask (claude/flask)
- Сделано: FastAPI → Flask (+ flask-cors). Контракт /health и /chat не изменился. Async-код (LLM, RAG, MCP) выполняется в одном фоновом event loop — `app/async_runner.py` (иначе клиенты GigaChat/OpenAI падают с «Event loop is closed» со второго запроса). Первые тесты: `backend/tests/test_api.py` (pytest + pytest-cov), 7 тестов, покрытие app 74%. Проверено вживую: фронт ↔ бэк ↔ GigaChat, несколько сообщений подряд.
- Дальше: Docker (docker compose: backend + frontend + Postgres с pgvector), тесты LLM-провайдеров, SPEC по ТЗ.
- Вопросы/блокеры: команда запуска на Render (задача деплоя) — `gunicorn`/`flask run`, решить при деплое.
- Что важно знать Codex: async-функции (retrieve, MCP) остаются async, контракт `retrieve` не менялся. Из синхронного кода вызывать через `app.async_runner.run(coro)`, не через `asyncio.run()`. Тесты — `backend/tests/`, запуск `uv run pytest --cov=app`.

## 2026-11-08 — каркас проекта (main, init)
- Сделано: правила (AGENTS.md, CLAUDE.md, .ai/), docs, backend FastAPI (/health, /chat, LLM-адаптер GigaChat + echo), frontend Next.js со страницей чата.
- Дальше: ждём ТЗ → /jmo-workflow:interview → docs/SPEC.md; деплой.
- Вопросы/блокеры: нет.
- Что важно знать Codex: заглушки для твоей зоны — `backend/app/rag/` и `backend/app/mcp_server/`. Контракт — `docs/API.md`.

## 2026-11-08 — сертификат GigaChat (claude/gigachat-cert)
- Сделано: корневой сертификат Минцифры в backend/certs/ (публичный, коммитится), GigaChat-адаптер подхватывает его автоматически — проверка SSL включена. Supabase-проект ai-buddy создан, pgvector включён. GigaChat проверен с локальной машины.
- Дальше: ждём ТЗ.
- Что важно знать Codex: Supabase URL/ключ и ключ GigaChat — в backend/.env, получи их у Миши лично. pgvector уже включён (схема extensions).
