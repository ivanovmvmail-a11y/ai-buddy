# Сервисы онбординга (101-T1/T3/T5)

Сервис отгулов на один день: [контракт и права](ABSENCE.md).

Демо-данные, не регламент Авито. Реализованы обычные async-функции Python с моделями
из `docs/specs/101-plan-next-step/plan.md` §3.1. Пользователи и связи наставников — только
из `app.agent.users.DEMO_USERS`. HTTP/агент подключены в T4; MCP/stdio реализован в T5.

## Вызов и хранение

```python
from app.async_runner import run
from app.agent.users import DEMO_USERS
from app.mcp_server.checklist import get_plan

plan = run(get_plan(DEMO_USERS["intern-anya"], "intern-anya"))
print(plan.model_dump(mode="json"))
```

Из async-кода функции вызываются через await. Из Flask/CLI — через общий `app.async_runner.run()`.
У пользовательских функций первый аргумент `actor: User`, у системных — внутренний SYSTEM_ACTOR. Объекты возвращаются в виде
pydantic-моделей, не разделяющих изменяемые данные с хранилищем.

`storage.OnboardingStore` — общий протокол для InMemoryStore и PostgresStore. `get_store()` кэшируется
на процесс: задан DATABASE_URL → DemoStore с ленивым PostgreSQL, пустое значение → память.
При первом чтении/записи DemoStore вызывает initialize(load_seed()) на общем event loop:
полностью пустая база заполняется, существующий прогресс сохраняется. Одновременные первые
запросы используют одну инициализацию. Если схема отсутствует или подготовка БД не удалась,
в лог пишется предупреждение и процесс продолжает с InMemoryStore(load_seed()). При отсутствии
таблиц лог подсказывает применить миграцию; пересоздание локального volume через
`docker compose down -v` удаляет его данные. Память сохраняет прогресс до перезапуска процесса,
затем он теряется. Для возврата на PostgreSQL после миграции/восстановления БД перезапустить backend.
Ошибки уже выполняемой сервисной транзакции откатываются и передаются вызывающему без повторной
записи в другое хранилище. `close()` закрывает пул на общем event loop.

`transaction()` сохраняет атомарность заявки, пункта, напоминаний и событий. Старые вызовы без
аргументов сохраняют полную изоляцию снимка, включая выданные наружу ссылки. Бизнес-сервисы используют
`transaction(include_events=False, copy_on_commit=False)`: старый журнал не копируется/не читается,
сохраняются изменения записей и новые события; результаты сервисов отделены от хранилища. Для памяти
остаётся одна копия доменных записей на запись, коммит использует сам снимок. Полный совместимый
режим нужен для явных административных операций/снимков, не для обычного чтения.

`read(include_events=False)` — внутреннее представление только для чтения доменных данных;
история событий загружается лишь по явному include_events=True (сводка недели/чтение журнала).
В этом режиме добавление/удаление событий вызывает RuntimeError в обоих хранилищах, в том числе
при python -O; транзакция откатывается. Обычный read без истории допускает новые события просмотра.
Память выдаёт ленивые Mapping/Sequence с отделёнными моделями, PostgreSQL — отдельные модели строк.
Представление read не сериализуется целиком в DTO. `get_plan` дописывает только два события
plan_viewed/next_step_shown по спецификации; прочие чтения событий не создают. Они не требуют
полного снимка журнала и не переписывают его. Проверка с 10 000 событиями запрещает deepcopy
истории на сервисных чтениях/записях и проверяет ровно два новых события на просмотр плана.

PostgresStore использует прямой psycopg и общий с RAG ленивый AsyncConnectionPool (1–8 соединений
суммарно на точный DATABASE_URL в процессе, менеджер app.db.pool) на app.async_runner; SELECT выполняются в согласованном снимке REPEATABLE READ, записи/
seed/reset сериализуются pg_advisory_xact_lock между процессами. Сохраняются только изменённые
строки, обычный журнал — append-only. Все шесть доменных таблиц имеют внутренний identity seq:
чтение сохраняет порядок вставки, обновление записи не меняет её место; seq не входит в DTO.
InMemoryStore использует asyncio.Lock на том же цикле. close() PostgreSQL-адаптера освобождает
его долю; физический пул закрывается только после последнего владельца. Поэтому fallback
онбординга не закрывает пул работающего RAG. Подробности — app/db/README.md.

## Seed и сброс

Единственный источник — `seed/onboarding.json`: 10 рабочих пунктов и 6 контуров на стажёра,
7 общих рабочих пунктов + 3 пункта команды, 4 ресурса, два разных профиля навыков и
стартовые заявки Ивана. Формулировки и задания можно менять в JSON без правки сервисов.
Поля формы заявки хранятся в `request_fields` и допускают отдельный `fields` у ресурса.
Обработка согласования определяется `resource.approver`, а не названием/типом ресурса.

Из backend:

```bash
uv run --frozen --offline python -m app.mcp_server.seed
uv run --frozen --offline python -m app.mcp_server.seed --reset
uv run --frozen --offline python -m app.mcp_server.seed --validate
```

По умолчанию CLI инициализирует выбранное хранилище **только если все семь таблиц пусты**. Существующий
прогресс, в том числе частично непустое хранилище, не перезаписывается. `--reset` заменяет данные всех
семи таблиц онбординга исходным состоянием в одной транзакции. С DATABASE_URL это именно база, а не
память команды. CLI работает с PostgreSQL напрямую: при ошибке seed/reset пишет предупреждение
и завершается с кодом 1, без сообщения об успешном сбросе в память. Сервер сам выбирает запасной
режим при обращении к нему. `--validate` только проверяет JSON, не открывая хранилище. Без DATABASE_URL команда
работает с памятью своего процесса. В серверной демо-панели вызывается `await clock.reset_demo(actor)`.
Сброс атомарно восстанавливает seed, очищает изменения/напоминания и пишет `demo_reset`.
Пользователи не дублируются в JSON: используются их id и команды из DEMO_USERS.

## Миграция и Docker

`supabase/migrations/20261111010000_onboarding.sql` создаёт intern_state, plan_items,
access_resources, access_requests, skill_profiles, reminders, events. Индексы защищают от
дубликата активной заявки и повторного напоминания на пункт; overdue/waiting_days вычисляются,
в БД не хранятся. RLS включён с закрытым доступом для непривилегированных клиентов; PUBLIC и
условно существующие anon/authenticated лишены прав на таблицы и все identity-последовательности.
Supabase-роли/функции не создаются и не требуются. Подключение backend — доверенный владелец
таблиц или служебная роль с BYPASSRLS; права конечных пользователей проверяют сервисы.

При первом создании volume Docker применяет миграции. Перед gunicorn backend запускает
`python -m app.mcp_server.seed`, затем загрузку RAG. Ошибка любого из этих шагов даёт предупреждение,
после чего gunicorn запускается. Если seed не сработал, первый запрос повторяет инициализацию;
при отсутствии таблиц или ошибке подготовки PostgreSQL демонстрация работает на памяти.
Повторный старт при рабочей БД сохраняет прогресс.
Для уже существующей локальной базы применить новую миграцию, затем перезапустить backend:

```bash
docker compose exec -T db psql -v ON_ERROR_STOP=1 -U buddy -d ai_buddy < supabase/migrations/20261111010000_onboarding.sql
docker compose up --build --detach
```

Сброс выбранной базы: `docker compose exec backend python -m app.mcp_server.seed --reset`.
Облачную миграцию применяет Claude после мержа. AC-5 проверяет смену отдельных Python-процессов:
день, статус, заявка, профиль и напоминания сохраняются; повторный seed не стирает изменения.

## Доступ и результаты

- `checklist.get_plan(actor, intern_id)` → Plan. Стажёр видит свой, наставник — своих,
  назначенный руководитель (`lead_id`) — своих стажёров, куратор — всех. HR BP не видит планов.
  Связь со стажёром проверяет общий can_view_intern, поверх него сохраняются ограничения ролей сервиса.
- `set_item_status(actor, item_id, status, reason=None)` → PlanItem. Только ответственный;
  наставник может вернуть закрытый ручной пункт своего стажёра в работу с непустой причиной.
  Пункты с ресурсом и этапы-контуры запрещено менять вручную. Повтор того же статуса — без события;
  переход обратно в not_started запрещён, из done можно перейти только в in_progress.
- `weekly_summary(actor, intern_id, week)` → dict с `intern_id`, `week`, `closed` (факты событий
  с item_id/title/day), `access_granted` (факты с request_id/resource_id/day), `carry_over` (PlanItem).
  Статус и метаданные пункта восстанавливаются по последнему событию на конец запрошенной недели
  (или текущий день, если неделя ещё идёт). Возвращённый в работу пункт не бывает одновременно
  в closed и carry_over; действия следующих недель не меняют старую сводку. Неделя — положительное
  целое, факты выбираются по демо-дню, баллов и рейтингов нет.
- `access.list_resources(actor)` и `create_request(actor, resource_id, level, justification)` доступны
  только стажёру. Авто-заявка сразу granted, согласуемая — pending_approval и пункт waiting.
  Активная/выданная заявка на тот же ресурс конфликтует; после отказа разрешена новая.
- `list_requests(actor, intern_id=None)` → список, новые сверху: стажёр видит свои, наставник — своих.
  `decide_request(actor, request_id, approve, reason=None)` → AccessRequest, только назначенный
  наставник. Отказ требует причины, пункт возвращается in_progress; решение завершает напоминание.
- `hiring.get_skill_profile` — стажёр себе/наставник своим, `set_skill_level` — только наставник своему.
  T4 не должен предлагать set_skill_level как инструмент ИИ: изменение уровня — действие наставника.
- Чужой объект и отсутствующий дают одинаковый `NotFound("Не найдено")`. Для видимого объекта
  запрещённое действие — `Forbidden`; неверный переход — `Conflict`; неверные значения —
  pydantic.ValidationError. Отказы не оставляют частичных изменений или событий.

Один PlanItem содержит один resource_id: базовый пункт связан с Jira; Confluence — отдельный ресурс,
заявка на него может не иметь plan_item_id. Это уточнение для последующей спеки 103.

## Часы и системные функции

Демо-панель намеренно доступна любой из восьми демо-ролей: `get_day(actor, intern_id)` → int,
`advance_day(actor, intern_id=None)` → dict `intern_id: новый_день` (None — все),
`reset_demo(actor)` → None. Это инструменты демонстрации, не права на чтение чужих планов/профилей.
Временные метки предметных событий/изменений используют виртуальную дату стажировки (полдень UTC).

`cron_tick(actor, day=None)` → новые Reminder. Без day используются отдельные часы каждого
стажёра; явно переданный day задаёт день проверки, не двигая часы. Напоминание создаётся
единожды на пункт: ожидание заявки ≥ 2 дней либо просрочка; адресат — стажёр или ответственный.
Для waiting с заявкой действует только порог ожидания, ранняя просрочка не занимает слот напоминания.
`list_reminders(actor)` возвращает только свои, включая историю статусов, а
`snooze_reminder(actor, id, days=1)` и `done_reminder(actor, id)` доступны только владельцу.
По окончании snooze оживает тот же объект; завершённое напоминание повторно не создаётся.

`events.log_event(actor, type, payload)`, `events.list_events(actor, intern_id=None, type=None)` и
`clock.cron_tick` принимают только внутренний singleton SYSTEM_ACTOR (id="system", role="system").
Отдельная замороженная модель SystemActor находится в зоне MCP; User/Role/DEMO_USERS агента
не менялись. Обычный вызов любой из восьми ролей, поддельный User или копия SystemActor получают
Forbidden. Для доверенного планировщика:

```python
from app.mcp_server._system import SYSTEM_ACTOR
from app.mcp_server import clock

reminders = await clock.cron_tick(SYSTEM_ACTOR)
```

SYSTEM_ACTOR нельзя получать из JSON/HTTP или предлагать как инструмент агента. ContextVar-флага
больше нет. Работа крона, авто-согласование и автоматическое завершение напоминаний пишутся от
system; ручные действия — от пользователя. События действий с напоминаниями плана содержат
intern_id и виртуальный day, поэтому фильтруются по стажёру и имеют виртуальную дату.
Бизнес-функции сами проверяют права и записывают события в своей транзакции. Изменения сигнатур
относительно сокращений в plan.md перечислены в HANDOFF. Транспорт не экспортирует приватные функции.

## MCP: один пользователь на stdio-процесс

Официальный SDK mcp/FastMCP установлен только с extra mcp; обычный веб-образ Docker/Railway
его не включает. Из backend:

```bash
uv sync --frozen --extra mcp
uv run --extra mcp python -m app.mcp_server.server --user intern-anya
```

Вместо --user можно задать MCP_USER_ID в окружении процесса. Флаг --user имеет приоритет;
пустое/неизвестное значение останавливает процесс с кодом 2 и понятным сообщением в stderr
до запуска MCP-транспорта. Значение из .env можно загрузить через
`uv run --env-file .env --extra mcp python -m app.mcp_server.server`.

Личность выбирает человек, который настраивает запуск MCP-клиента. Сервер один раз разрешает
id по DEMO_USERS: intern-anya, intern-ivan, mentor-petr, mentor-maria, lead-olga, lead-sergey,
hrbp-elena, curator-dmitry. Все вызовы этого процесса используют того же пользователя;
аргументов user_id/actor/role/team в инструментах нет. Клиент не может подать заявку как стажёр,
а затем одобрить её как наставник. Сервис проверяет права привязанного пользователя на объект.
Это имитация входа для локального демо, не корпоративная аутентификация.

Процесс ждёт MCP JSON-RPC на stdin и отвечает в stdout; диагностика идёт в stderr. SDK и сервисы
запускаются на общем app.async_runner. Сессии не закрывают общий пул: main закрывает хранилище
после завершения stdio, включая ошибку транспорта. Отдельный HTTP-порт, ключ LLM и Flask не нужны.

| Инструмент | Аргументы |
|---|---|
| get_plan | intern_id |
| set_item_status | item_id, status, reason? |
| list_resources | — |
| create_request | resource_id, level, justification |
| list_requests | intern_id? (без него — все доступные связанному пользователю заявки) |
| decide_request | request_id, approve (JSON boolean), reason? (обязателен при отказе) |
| get_skill_profile | intern_id |
| list_reminders | — (только активные личные напоминания, как HTTP /reminders) |

status: not_started / in_progress / waiting / done; level: read / edit / admin. Допустимость
перехода/согласования проверяют сервисы. set_item_status и decide_request имеют destructiveHint=true;
create_request — destructiveHint=false, idempotentHint=false. Эти инструменты изменяют данные
при вызове; подтверждение клиента и HTTP-черновики агента — отдельные механизмы.
SYSTEM_ACTOR, cron_tick, log_event, set_skill_level и административный reset не зарегистрированы.

Ответы — CallToolResult: модели в structuredContent и JSON-представление в content. Списки —
structuredContent.result. Доменные ошибки дают isError=true; чужой и отсутствующий объект —
одинаковое «Не найдено». Неожиданные ошибки не раскрывают SQL/реквизиты подключения.

### Claude Desktop

Добавить сервер в claude_desktop_config.json (macOS: ~/Library/Application Support/Claude/;
Windows: %APPDATA%\Claude\), затем перезапустить Claude Desktop:

```json
{
  "mcpServers": {
    "ai-buddy-onboarding": {
      "command": "uv",
      "args": [
        "--directory", "/absolute/path/to/ai-buddy/backend",
        "run", "--frozen", "--extra", "mcp", "python", "-m", "app.mcp_server.server"
      ],
      "env": {
        "MCP_USER_ID": "intern-anya",
        "DATABASE_URL": "",
        "LLM_PROVIDER": "echo",
        "PYTHONUTF8": "1"
      }
    }
  }
}
```

Заменить каталог абсолютным путём к backend, а command — путём к uv, если Desktop не видит его
в PATH. На Windows в JSON используются пути вида C:\\projects\\ai-buddy\\backend.
Для другого пользователя изменить MCP_USER_ID в настройках запуска и перезапустить процесс.
DATABASE_URL="" выбирает память, переопределяя .env-БД. Для общего прогресса stdio-процессу
и Flask нужен один DATABASE_URL с миграцией; память раздельная по процессам и теряется при рестарте.

В любом stdio-клиенте указать те же command/args/env. После initialize и tools/list вызвать
get_plan с {"intern_id":"intern-anya"}. Пользователь не передаётся через tools/call.

### Пример SDK-клиента

Из backend с extra mcp:

```python
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from app.async_runner import run

async def inspect_plan():
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "app.mcp_server.server"],
        env={"MCP_USER_ID": "intern-anya", "DATABASE_URL": "", "LLM_PROVIDER": "echo"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            result = await client.call_tool("get_plan", {"intern_id": "intern-anya"})
            print(result.structuredContent)

run(inspect_plan())
```

## Тесты

```bash
cd backend
LLM_PROVIDER=echo uv run --extra mcp --frozen --offline pytest --cov=app --cov-branch --cov-report=term-missing
```

`tests/mcp/` проверяет прикладную часть AC-1…AC-11, матрицу прав для восьми пользователей,
атомарность и конкурентные заявки, профили, события, часы и отсутствие дублей напоминаний.
Обычные тесты не требуют ключей, сети, базы или Docker. Для общего набора на обоих хранилищах:

```bash
LLM_PROVIDER=echo uv run --extra mcp --frozen --offline pytest --mcp-postgres --cov=app --cov-branch --cov-report=term-missing
```

Нужен Docker (включая Docker Desktop) и уже скачанный pgvector/pgvector:pg17; тесты сами не скачивают
образ и не используют DATABASE_URL реальной базы. Фикстура уважает DOCKER_HOST/TLS/context, создаёт/удаляет только свой контейнер;
каждый общий тест с хранилищем запускается на памяти и PostgreSQL. Дополнительно проверяются
условные REVOKE/RLS на чистой БД с API-ролями и без, конкуренция двух пулов, настоящий SQL-откат,
lazy-пул на общем цикле, CLI seed/reset и AC-5 между процессами. Сквозной HTTP/интерфейс — T4.

Регрессии ревью #21 — test_pr21_regressions.py: запуск CMD после сбоя seed/RAG; HTTP /health и /plan
с настоящей фабрикой на пустых таблицах и БД со старой RAG-схемой; запись прогресса в fallback,
отсутствие повторной инициализации/перезаписи, порядок записей, запрет append истории при python -O.
Проверка Linux CMD через /bin/sh пропускается на Windows; остальные проверки и Docker CLI переносимы.

Протокол MCP: tests/mcp/test_protocol.py соединяет ClientSession с FastMCP через память,
проверяет привязку пользователя к запуску, невозможность смены роли/самосогласования, все 8 ролей,
активные личные напоминания, одинаковый NotFound, подсказки мутаций и две сессии без закрытия пула.
Подпроцессы проверяют ошибку запуска без пользователя, приоритет --user над MCP_USER_ID и реальные
вызовы по stdio. С --mcp-postgres общие сценарии также работают на временном PostgreSQL.
Без extra mcp протокольный модуль тестов пропускается, остальной backend работает без SDK.
