# Демо-панель Grafana

`docker compose up --build` поднимает Grafana на http://localhost:3002 с готовым источником PostgreSQL
и панелью «AI-buddy — польза вживую» (`/d/ai-buddy-demo`). Ручной импорт JSON/настройка datasource не нужны.
Данные синтетические. Обновление каждые 5 секунд; по умолчанию период — последние 7 дней.

Панель показывает вопросы по дням, долю закрытых без человека, долю ответов с источником,
полезные/неполезные оценки, среднее время ответа, частые темы, темы без ответа и текущее количество
закрытых пунктов недели 1. Последний показатель не зависит от выбранного периода.
Формула «закрыто без человека» совпадает с app/agent/analytics.py: источник или данные сервиса,
без отказа, «нет в базе» и HR. Учитываются только события стажёров (есть intern_id).

## Вход

Без корневого .env — anonymous Viewer, панель не редактируется; стандартный admin/admin не создаётся.
Чтобы включить вход администратора, скопировать корневой .env.example в .env и заполнить обе строки:

```dotenv
GRAFANA_ADMIN_USER=
GRAFANA_ADMIN_PASSWORD=
```

Пароль задаётся пользователем только в .env; не публиковать его в git. Если заполнена только одна
строка, остаётся anonymous Viewer. Начальные credentials создаются при первом запуске с ними;
существующий пароль Grafana меняется через её интерфейс/CLI, а не заменой env.
Anonymous Viewer — общий обезличенный обзор локального демо, без разграничения по наставникам.
Ролевые метрики приложения /metrics по-прежнему проверяет backend.

## Подключение и права

Grafana читает три представления grafana_answers/grafana_feedback/grafana_plan_progress. В них нет
имён, user_id, intern_id, team, полного payload или текста вопросов/ответов. У пользователя
ai_buddy_grafana только SELECT этих представлений, без доступа к исходным таблицам и без BYPASSRLS.
Default transaction read-only дополнителен к SQL-grants; даже отключение этого флага не даёт права записи.
Миграция `20261111103913_grafana_revoke_api_roles.sql` отдельно отзывает все прямые grants
на эти представления у существующих anon/authenticated: прямые grants от default privileges
Supabase не снимаются через REVOKE FROM PUBLIC. Доступ ai_buddy_grafana сохраняется. К облачной БД миграцию применяет
Claude после мержа; повторный CREATE OR REPLACE VIEW в grafana-init сохраняет закрытые ACL.

Одноразовый grafana-init использует только локальный Docker PostgreSQL, применяет идемпотентную
SQL-миграцию и выдаёт роли случайный пароль. Пароль хранится в отдельном Docker volume, передаётся
datasource через secureJsonData, не печатается и не попадает в аргументы процессов. Соединений Grafana — не более 2.
Backend/.env и облачная DATABASE_URL в Grafana не передаются. Панель показывает события именно
локальной PostgreSQL; прогресс backend в запасной памяти не попадает в неё.

Существующий том БД не требуется удалять. Если таблиц онбординга пока нет, представления пустые,
панель работает с нулями. После применения миграции онбординга повторить
`docker compose run --rm grafana-init`, затем `docker compose up --detach grafana`:
представления начнут читать настоящие таблицы. Повторный init не стирает события/планы.

Для Grafana отдельно сохраняется grafana-data; `docker compose down -v` удаляет и его, и данные приложения.
Облачную миграцию при необходимости применяет Claude после мержа, текущий PR реальную БД не меняет.

## Проверки

```bash
curl --fail http://localhost:3002/api/health
curl --fail http://localhost:3002/api/dashboards/uid/ai-buddy-demo
curl --fail http://localhost:3002/api/datasources/uid/ai-buddy-postgres/health
cd backend
LLM_PROVIDER=echo uv run --extra mcp --frozen --offline pytest tests/mcp/test_grafana.py --mcp-postgres
```

Последние два HTTP-запроса приведены для anonymous Viewer; с администратором требуется авторизация.
CI проверяет здоровье, готовую панель и успешное соединение с PostgreSQL после compose up.
SQL-тесты запускают все запросы JSON-панели ограниченной ролью, сверяют формулу, запрещают чтение
приватных таблиц и запись, проверяют повторный init и старую БД без onboarding-таблиц.
