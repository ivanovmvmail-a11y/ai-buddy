# 101 — План стажёра, статусы и следующий шаг: план реализации

## 1. Подход
Имитации корпоративных сервисов (чек-лист новичка, доступы, найм, ИИ-крон) живут в `backend/app/mcp_server/`
как **обычные async-функции на Python** с проверкой прав внутри. Их вызывают и агент (через `ToolRegistry`),
и HTTP-эндпоинты для интерфейса. MCP-обёртка над теми же функциями — отдельная задача (T5): протокол MCP
показываем, но логика от него не зависит и тестируется без сети.
Хранилище — интерфейс с двумя реализациями: в памяти (тесты, запуск без базы) и PostgreSQL по `DATABASE_URL`
(как в RAG). Синтетические данные — один seed-файл, из него заполняются обе реализации.

Почему в одном PR сразу план, доступы, профиль и часы: статусы плана меняются событиями заявок и хода времени,
а профиль нужен объяснениям. Делить контракт на части — значит дважды менять одни и те же таблицы.
Поведение доступов, профиля и напоминаний уточнят спеки 103, 104, 301, но контракт ниже уже их покрывает.

## 2. Что меняется
| Часть | Файлы / модули | Чья зона |
|---|---|---|
| Имитации сервисов | `backend/app/mcp_server/` (модели, сервисы, хранилища, seed) | Codex |
| База | `supabase/migrations/<ts>_onboarding.sql` | Codex |
| HTTP для интерфейса | `backend/app/main.py`: `/plan`, `/requests`, `/reminders`, `/demo/*` | Claude |
| Инструменты агента, промпт | `backend/app/agent/` | Claude |
| Интерфейс | `frontend/` | Claude |
| Контракт | `docs/API.md` — отдельный PR `[API]` | Claude |

## 3. Данные и контракты

### 3.1. Модели (pydantic, `app/mcp_server/models.py`)
```python
Stage = Literal["week1", "week2", "month1", "month2", "after3m"]       # week1/week2 рабочие, остальные — контур
OwnerRole = Literal["intern", "mentor", "lead"]
ItemStatus = Literal["not_started", "in_progress", "waiting", "done"]   # «просрочен» не хранится, вычисляется
SkillLevel = Literal["novice", "familiar", "confident"]
AccessLevel = Literal["read", "edit", "admin"]
RequestStatus = Literal["created", "pending_approval", "granted", "rejected"]

class PlanItem(BaseModel):
    id: str                    # стабильный, напр. "anya.w1.access-base"
    intern_id: str
    stage: Stage
    order: int
    title: str                 # «Запросить базовые доступы»
    summary: str               # 1–2 предложения, своими словами
    owner_role: OwnerRole
    topic: str | None          # ключ темы карты навыков: "git", "sql", "ci", ...
    doc_source_id: str | None  # source_id документа RAG, напр. "demo:01-onboarding.md"
    resource_id: str | None    # ресурс доступа → пункт закрывается только сервисом
    due_day: int | None        # срок: день стажировки
    practice: str | None       # короткое практическое задание
    status: ItemStatus
    status_reason: str | None  # причина возврата наставником
    updated_at: datetime
    updated_by: str | None
    overdue: bool              # вычисляется: status != done и current_day > due_day
    waiting_for: str | None    # id человека, которого ждём (для status=waiting)
    waiting_days: int | None

class StageInfo(BaseModel):
    stage: Stage
    title: str                 # «Недели 1–2», «Месяц 1», ...
    total: int
    done: int
    state: Literal["passed", "current", "ahead"]

class NextStep(BaseModel):
    item: PlanItem | None                 # None — нечего делать самому
    waiting: list[PlanItem]               # пункты, где ждём других (для «кого ждём и сколько дней»)

class Plan(BaseModel):
    intern_id: str
    current_day: int
    items: list[PlanItem]                 # все этапы; month1+ — без действий
    ladder: list[StageInfo]               # «Недели 1–2» = week1 + week2 одной ступенью
    next_step: NextStep                   # считается для того, кто смотрит (actor)

class AccessResource(BaseModel):
    id: str                    # "jira", "confluence", "bitbucket-platform", ...
    title: str
    kind: Literal["base", "team_space"]
    team: str | None           # None — общий
    approver: Literal["auto", "mentor"]   # поле ресурса, не правило в коде
    fields: list[dict]         # настраиваемый список полей заявки: name, label, type, options?, default?

class AccessRequest(BaseModel):
    id: str                    # "REQ-1001" — номер, который видит стажёр
    intern_id: str
    resource_id: str
    level: AccessLevel
    justification: str
    status: RequestStatus
    approver_id: str | None
    reject_reason: str | None
    plan_item_id: str | None
    created_day: int
    created_at: datetime
    updated_at: datetime

class SkillProfile(BaseModel):
    intern_id: str
    skills: dict[str, SkillLevel]   # тема → уровень
    strengths: list[str]
    growth: list[str]               # «темы для роста», не «слабости»
    updated_by: str | None
    updated_at: datetime

class Reminder(BaseModel):
    id: str
    user_id: str               # кому показываем
    plan_item_id: str | None
    request_id: str | None
    text: str
    status: Literal["active", "snoozed", "done"]
    created_day: int
    snooze_until_day: int | None
```

### 3.2. Функции сервисов
Все async, первым аргументом — `actor: app.agent.users.User`. Права проверяет сама функция (MCP-сервер не
доверяет вызывающему). Ошибки — из `app/mcp_server/errors.py`:
`NotFound` (нет **или нет доступа** — не раскрываем факт существования), `Forbidden` (видно, но действие
запрещено, например стажёр отмечает пункт наставника), `Conflict` (неверный переход статуса), `ValidationError` pydantic.

| Модуль | Функция | Кто может | Что делает |
|---|---|---|---|
| `checklist` | `get_plan(actor, intern_id)` | стажёр — свой; наставник — своих; руководитель — своей команды; куратор — всех | план + лестница + следующий шаг для `actor` |
| `checklist` | `set_item_status(actor, item_id, status, reason=None)` | ответственный за пункт; наставник может вернуть пункт стажёра `done → in_progress` только с `reason` | пункт с `resource_id` вручную не меняется → `Forbidden` |
| `checklist` | `weekly_summary(actor, intern_id, week)` | те же, кто видит план | факты из событий: закрыто, получены доступы, переходит дальше |
| `access` | `list_resources(actor)` | стажёр | общие ресурсы + ресурсы своей команды |
| `access` | `create_request(actor, resource_id, level, justification)` | только стажёр, себе | `approver=auto` → сразу `granted`, пункт `done`; `mentor` → `pending_approval`, пункт `waiting`, `approver_id` = наставник |
| `access` | `list_requests(actor, intern_id=None)` | стажёр — свои; наставник — своих стажёров | новые сверху |
| `access` | `decide_request(actor, request_id, approve, reason=None)` | только `approver_id` | `granted` → пункт `done`; `rejected` (причина обязательна) → пункт `in_progress` с причиной |
| `hiring` | `get_skill_profile(actor, intern_id)` | стажёр — свой; наставник — своих | руководитель, куратор, HR BP → `NotFound` |
| `hiring` | `set_skill_level(actor, intern_id, topic, level)` | только наставник своего стажёра | ИИ уровень не меняет |
| `clock` | `get_day(intern_id)`, `advance_day(actor, intern_id=None)` | демо-панель, любая роль | день +1 (всем стажёрам, если `intern_id` не задан) и запуск `cron_tick` |
| `clock` | `cron_tick(day)` | система | напоминания: заявка ждёт ≥ 2 дней → стажёру «напомнить наставнику?»; пункт просрочен → ответственному. **Одно напоминание на пункт**, повторно не создаётся |
| `clock` | `list_reminders(actor)`, `snooze_reminder(actor, id, days=1)`, `done_reminder(actor, id)` | владелец напоминания | |
| `clock` | `reset_demo()` | демо-панель | вернуть стартовое состояние из seed |
| `events` | `log_event(user, type, payload)`, `list_events(...)` | система | таблица в стиле Clickstream: `ts, user_id, role, team, type, payload jsonb` |

Каждая функция, которая что-то меняет, пишет событие: `plan_item_status_changed`, `access_request_created`,
`access_request_decided`, `skill_level_changed`, `day_advanced`, `reminder_created`.

**Следующий шаг** (`next_step` для `actor`): пункты рабочих этапов (`week1`, `week2`) этого стажёра, где
`owner_role` = роль `actor` и статус не `done` и не `waiting`; сначала просроченные, затем по `stage`, `order`.
Первый — `item`. Пункты в `waiting` — список `waiting` с `waiting_for` и `waiting_days`.

**Лестница:** ступени `«Недели 1–2»` (week1+week2), `«Месяц 1»`, `«Месяц 2»`, `«После 3 месяцев»`.
`passed` — все пункты ступени `done`; `current` — первая не пройденная; остальные `ahead`.

### 3.3. Хранилище
Интерфейс `OnboardingStore` (`app/mcp_server/storage.py`), реализации `InMemoryStore` и `PostgresStore`.
Фабрика `get_store()` кэшируется на процесс: есть `DATABASE_URL` → PostgreSQL, нет → память (с предупреждением в
логе). Таблицы: `intern_state` (intern_id, start_date, current_day), `plan_items`, `access_resources`,
`access_requests`, `skill_profiles`, `reminders`, `events`. Миграция — на чистом PostgreSQL, без Supabase-ролей
(правила из HANDOFF 2026-11-10), права `anon/authenticated` отозваны, как в RAG.
Seed: `app/mcp_server/seed/onboarding.json`, загрузка `uv run python -m app.mcp_server.seed` (идемпотентно;
`--reset` — стартовое состояние). В Docker — автоматически при старте, как загрузка документов RAG.

### 3.4. Синтетические данные (seed)
- Стажёры из `app/agent/users.py`: Аня (Платформа объявлений, наставник Пётр, день 2), Иван (Авито Доставка,
  наставник Мария, день 8).
- Недели 1–2: общий каркас из таблицы `docs/SPEC.md` 3.1 + 2–3 пункта команды. Названия сервисов из вебинара:
  Mattermost, Jira, Confluence, Bitbucket, Grafana, Redash.
- Ресурсы: `jira`, `confluence` (base, auto); `bitbucket-platform`, `bitbucket-delivery` (team_space, mentor) —
  поля заявки: ресурс, обоснование, уровень прав (по умолчанию `read`), кто согласует.
- Аня: закрыт «Познакомиться с командой», остальное `not_started`. Иван: базовые доступы `done`, заявка в
  пространство команды `pending_approval` 3 дня, один пункт недели 1 со сроком 5 не закрыт (просрочен).
- Профили: Аня — `git: novice`, `sql: confident`; Иван — `git: confident`, `sql: novice` (один и тот же вопрос
  про Git даёт разную глубину ответа). Сильные стороны и темы для роста — 2–3 строки, без баллов.
- Тексты — пересказ своими словами, с пометкой «демо-данные, не регламент Авито».

## 4. Проверка
- Codex: `backend/tests/mcp/` — все AC спеки 101 + права из таблицы 3.2 для всех 8 демо-пользователей, на
  `InMemoryStore`; те же тесты на PostgreSQL по флагу, как `--rag-postgres`. Покрытие backend > 80%.
- Claude: HTTP-тесты эндпоинтов, тесты инструментов агента, Vitest на интерфейс плана.
- Вручную: демо-маршрут `docs/SPEC.md` раздел 14, шаги 1–6.

## 5. Риски и запасной вариант
- Не успеваем PostgreSQL-реализацию к 13.11 → демо на `InMemoryStore` (данные теряются при перезапуске —
  критерий «сохраняется после перезапуска» тогда закрываем позже).
- Не успеваем MCP-обёртку (T5) → показываем функции и схему «заменяется на MCP», протокол — после чекпоинта.

## 6. Что заменяется при внедрении в Авито
Функции `checklist`/`access`/`hiring`/`clock` → вызовы настоящих MCP-серверов (чек-лист новичка, система заявок,
найм, ИИ-крон) с той же сигнатурой; `InMemoryStore`/`PostgresStore` уходят вместе с имитациями;
`events` → Clickstream/Kafka. Агент и интерфейс не меняются.
