# Журнал Claude

Формат записи (новые сверху):
```
## ГГГГ-ММ-ДД — <задача> (ветка)
- Сделано:
- Дальше:
- Вопросы/блокеры:
- Что важно знать Codex:
```

## 2026-11-10 — шаблон SDD (claude/sdd-template)
- Сделано: `docs/specs/README.md` (процесс, нумерация), `_template.md`, первая спецификация `001-agent-tools.md` (механика инструментов, 10 критериев приёмки с трассировкой на автотесты из PR «[API] Инструменты агента»).
- Дальше: спецификации сценариев `1xx` после интервью.

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
