# AI-buddy

ИИ-помощник для стажёров Авито: помогает быстрее освоиться в команде и приступить к работе.
Хакатон, трек Web/AI.

**Правила работы для людей и ИИ — в [AGENTS.md](AGENTS.md).** Доска задач — [.ai/STATUS.md](.ai/STATUS.md).

## Запуск через Docker (основной способ)

Нужен только [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up --build
```

- сайт — http://localhost:3000
- backend — http://localhost:8000/health
- база PostgreSQL + pgvector — `localhost:5432`, тестовые учётные данные `buddy` / `buddy`, база `ai_buddy`

**Без ключей** всё запускается в демо-режиме: вместо нейросети отвечает заглушка `echo`.
Чтобы подключить нейросеть: `cp backend/.env.example backend/.env`, указать `LLM_PROVIDER` и ключ (см. «Подключение GigaChat»), перезапустить `docker compose up --build`.

Остановить: `docker compose down`. Стереть базу и начать с нуля: `docker compose down -v`.

## Запуск для разработки (без Docker)

Нужны: [Git](https://git-scm.com), [Node.js LTS](https://nodejs.org), [uv](https://docs.astral.sh/uv/).

```bash
# 1. Backend (http://localhost:8000/health)
cd backend
cp .env.example .env        # и заполнить ключи
uv sync
uv run flask --app app.main run --debug --port 8000

# 2. Frontend (http://localhost:3000) — в другом терминале
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Без ключей backend работает в режиме `LLM_PROVIDER=echo` (повторяет сообщение), чтобы интерфейс можно было делать сразу.

## Подключение GigaChat
1. [developers.sber.ru/studio](https://developers.sber.ru/studio) → создать проект GigaChat API → скопировать **Authorization Key**.
2. В `backend/.env`: `LLM_PROVIDER=gigachat`, `GIGACHAT_CREDENTIALS=<ключ>`.
3. Сертификат Минцифры уже лежит в репозитории (`backend/certs/russian_trusted_root_ca.cer`, источник — [gosuslugi.ru/crt](https://www.gosuslugi.ru/crt)) и подключается автоматически. Ничего делать не нужно.

## Структура
```
backend/app/
  main.py         Flask: /health, /chat
  async_runner.py общий event loop для async-кода (LLM, RAG, MCP)
  agent/          логика агента, промпты           (Claude)
  llm/            провайдеры LLM: gigachat|openai|echo (Claude)
  rag/            поиск по документам команды      (Codex)
  mcp_server/     MCP-инструменты к корп. сервисам (Codex)
  db/             Supabase                          (Codex)
frontend/src/     Next.js, страница чата            (Claude)
docs/             SPEC, API, DECISIONS, SETUP_TEAMMATE
.ai/              STATUS + журналы агентов
```

## Проверка
- `GET http://localhost:8000/health` → `{"status":"ok", ...}`
- На http://localhost:3000 отправить сообщение — приходит ответ.
- Тесты backend: `cd backend && uv run pytest --cov=app --cov-report=term-missing`
