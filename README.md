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
- Grafana — http://localhost:3002, [готовая панель и настройки входа](ops/grafana/README.md)
- база PostgreSQL + pgvector — внутри Docker (порт наружу не открыт, чтобы не мешать установленному у вас PostgreSQL); консоль: `docker compose exec db psql -U buddy -d ai_buddy` (тестовые учётные данные `buddy` / `buddy`)

**Без ключей** всё запускается в **сценарном режиме** (`LLM_PROVIDER=scenario`, спека [003](docs/specs/003-scenario-mode/spec.md)): весь маршрут демо проходится — следующий шаг по плану, черновик заявки на доступ с подтверждением, отказ на чужие данные, ответ по документам с источником, «в базе нет» с черновиком вопроса наставнику. Ответы собираются из данных сервисов и документов, без нейросети; в интерфейсе это подписано.
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

Без ключей backend работает в сценарном режиме `LLM_PROVIDER=scenario`. Для разработки есть `LLM_PROVIDER=echo` — просто повторяет сообщение.

## Тестовые пользователи и вход (имитация)

В Авито авторизация и ролевая модель уже есть, поэтому в прототипе вход **имитирован**: пользователь передаётся заголовком `X-User-Id` (без заголовка — демо-стажёр `intern-anya`). Это сделано для проверки сценариев, а не как механизм безопасности: в проде заголовок заменяется корпоративным SSO (`backend/app/agent/users.py` — единственное место подмены). Все данные синтетические.

| id | Имя | Роль | Команда |
|---|---|---|---|
| `intern-anya` | Аня Смирнова | стажёр (наставник — Пётр) | Платформа объявлений |
| `intern-ivan` | Иван Кузнецов | стажёр (наставник — Мария) | Авито Доставка |
| `mentor-petr` | Пётр Волков | наставник | Платформа объявлений |
| `mentor-maria` | Мария Орлова | наставник | Авито Доставка |
| `lead-olga` | Ольга Новикова | руководитель | Платформа объявлений |
| `lead-sergey` | Сергей Лебедев | руководитель | Авито Доставка |
| `hrbp-elena` | Елена Морозова | HR BP | HR |
| `curator-dmitry` | Дмитрий Соколов | куратор стажировки | Avito Start |

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
  llm/            провайдеры LLM: gigachat|openai|scenario|echo (Claude)
  rag/            поиск по документам команды      (Codex)
  mcp_server/     MCP-инструменты к корп. сервисам (Codex)
  db/             Supabase                          (Codex)
frontend/src/     Next.js, страница чата            (Claude)
docs/             SPEC, API, DECISIONS, SETUP_TEAMMATE
.ai/              STATUS + журналы агентов
```

## Проверка
Каждый PR автоматически проверяет GitHub Actions (`.github/workflows/ci.yml`): тесты и покрытие backend (отчёт — артефакт `coverage-backend`), линтер и сборка frontend, запуск всего проекта через `docker compose up`.

- `GET http://localhost:8000/health` → `{"status":"ok", ...}`
- На http://localhost:3000 отправить сообщение — приходит ответ.
- Тесты backend: `cd backend && uv run pytest --cov=app --cov-report=term-missing`
- Тесты frontend с покрытием: `cd frontend && npm run test:cov` (порог — 80% строк)
- Золотой набор (37 контрольных вопросов, метрики качества): `cd backend && uv run python -m golden.run` — отчёты [сценарный режим](docs/golden-report.md), [GigaChat](docs/golden-report-gigachat.md)

## Облако (бонус): всё на Railway
- **Сайт:** https://ai-buddy-site-production.up.railway.app
- **Backend:** https://ai-buddy-production-9970a770.up.railway.app (`/health`)
- **База:** Supabase (миграции уже применены), подключение через Session pooler.

Оба сервиса в одном проекте Railway, собираются из Docker-файлов и сами обновляются при мерже в `main`.
- `ai-buddy` (backend): Root Directory `/backend`, Healthcheck `/health`, домен на порт 8000. Variables: `PORT=8000`, `LLM_PROVIDER=gigachat`, `EMBEDDINGS_PROVIDER=fake`, `GIGACHAT_CREDENTIALS`, `DATABASE_URL` (Supabase → Connect → Direct → Session pooler), `FRONTEND_ORIGINS` = адрес сайта.
- `ai-buddy-site` (frontend): Root Directory `/frontend`, домен на порт 3000. Variables: `NEXT_PUBLIC_API_URL` = адрес backend, `PORT=3000`.

Почему не другие хостинги (проверено из России 11.11.2026): Render, `*.onrender.com` и `*.vercel.app` не открываются; Koyeb закрыл бесплатную регистрацию; Netlify отдаёт файлы больше ~14 КБ с зависанием, и сайт не загружается. Пробный период Railway — 30 дней / $5.
