# AI-buddy

ИИ-помощник для стажёров Авито: помогает быстрее освоиться в команде и приступить к работе.
Хакатон, трек Web/AI.

**Правила работы для людей и ИИ — в [AGENTS.md](AGENTS.md).** Доска задач — [.ai/STATUS.md](.ai/STATUS.md).

## Запуск за 2 минуты

Нужны: [Git](https://git-scm.com), [Node.js LTS](https://nodejs.org), [uv](https://docs.astral.sh/uv/).

```bash
# 1. Backend (http://localhost:8000/health)
cd backend
cp .env.example .env        # и заполнить ключи
uv sync
uv run fastapi dev app/main.py

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
3. Сертификат Минцифры (без него будет ошибка SSL): скачать `russian_trusted_root_ca.cer` с [gosuslugi.ru/crt](https://www.gosuslugi.ru/crt) и указать путь в `GIGACHAT_CA_BUNDLE_FILE`.
   Временный вариант для локальной проверки: `GIGACHAT_VERIFY_SSL=false`.

## Структура
```
backend/app/
  main.py         FastAPI: /health, /chat
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
