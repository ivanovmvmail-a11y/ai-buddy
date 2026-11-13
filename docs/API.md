# API — контракт frontend ↔ backend

Базовый URL: `http://localhost:8000` локально, на проде — `NEXT_PUBLIC_API_URL`.
Меняется только PR с пометкой `[API]`.

## Пользователь (имитация авторизации)
Все запросы, кроме `/health`, выполняются от имени пользователя из заголовка `X-User-Id`.
- Нет заголовка → `401` («Не указан пользователь…»): пользователь молча не подставляется.
- Неизвестный id → `401 {"detail": "Неизвестный пользователь"}`.

Общие ошибки — всегда JSON `{"detail": "…"}`: битое тело — `400` («Тело запроса — не JSON» / «Ожидается JSON-объект»);
неизвестный адрес — `404`; неподдерживаемый метод — `405`; тело больше 512 КБ — `413`; булевы поля (`approve`) —
только `true`/`false`, иначе `422`.

Демо-пользователи (синтетические): `intern-anya`, `intern-ivan` (стажёры), `mentor-petr`, `mentor-maria` (наставники),
`lead-olga`, `lead-sergey` (руководители), `hrbp-elena` (HR BP), `curator-dmitry` (куратор).
В Авито заголовок заменяется корпоративным SSO; список — в `backend/app/agent/users.py`.

## GET /health
Ответ `200`:
```json
{ "status": "ok", "llm_provider": "gigachat" }
```

## GET /me
Текущий пользователь. Ответ `200`:
```json
{ "id": "intern-anya", "name": "Аня Смирнова", "role": "intern", "team": "Платформа объявлений",
  "mentor_id": "mentor-petr", "lead_id": "lead-olga" }
```
`role`: `intern` | `mentor` | `lead` | `hrbp` | `curator`.

## POST /chat
Запрос:
```json
{
  "messages": [
    { "role": "user", "content": "Напомни 20 ноября запросить доступ к GitLab" }
  ]
}
```
`role`: `user` | `assistant` (`system` принимается, но игнорируется — системный промпт задаёт сервер).
История передаётся целиком.

Ответ `200`:
```json
{
  "reply": "Подготовил черновик напоминания. Проверь и нажми «Подтвердить».",
  "sources": [ { "title": "Онбординг-гайд", "url": null } ],
  "actions": [ <Action> ]
}
```
- `sources` — документы, найденные RAG.
- `actions` — **черновики**, которые агент подготовил в этом ответе (`status: "pending"`). Фронт показывает
  карточку с кнопками «Подтвердить» / «Отменить». Без подтверждения ничего не выполняется.

Ошибки: `422` — неверное тело запроса, пустое сообщение (последнее должно быть от `user` и не пустым), сообщение
длиннее 4000 символов или больше 40 сообщений истории; `502 {"detail": "Помощник временно недоступен. Попробуйте ещё раз через минуту."}` — сбой модели (детали — только в логе сервера).

## Action
```json
{
  "id": "act_dd9dd115ae1d",
  "user_id": "intern-anya",
  "tool": "create_reminder",
  "title": "Напоминание на 20.11.2026: запросить доступ к GitLab",
  "params": { "text": "запросить доступ к GitLab", "remind_on": "2026-11-20" },
  "status": "pending",
  "result": null,
  "error": null,
  "created_at": "2026-11-09T22:48:29.437281Z",
  "updated_at": "2026-11-09T22:48:29.437281Z"
}
```
`status`: `pending` (черновик) → `running` (выполняется прямо сейчас) → `done` (выполнено, `result` — ответ сервиса) |
`failed` (`error` — текст ошибки) | `cancelled`. Черновик подтверждается атомарно: из одновременных «Подтвердить»
выполняется одно, остальные получают `409`. `POST /demo/reset` удаляет все черновики и действия.

## GET /chat/history?limit=
Своя переписка с ботом, старые сверху (SPEC 9): вопросы в `/chat` и сценарные объяснения пункта. По умолчанию и максимум —
50 последних сообщений. Чужую историю получить нельзя (пользователь — из `X-User-Id`). `POST /demo/reset` очищает историю.
```json
{ "messages": [ { "id": "msg_…", "role": "user" | "assistant", "content": "…", "sources": [{"title": "…", "url": null}],
                  "answer_id": "ans_…" | null, "scripted": false, "created_at": "…" } ] }
```
Интерфейс при входе показывает эту историю и неподтверждённые черновики (`GET /actions`), а затем приветствие; последнего
вошедшего пользователя помнит браузер. Тексты хранятся только для самого пользователя — в аналитику идут лишь темы.

## GET /documents?title=
Текст документа из «Источник» — для окна просмотра в интерфейсе (проверка 12.11: ссылки вели на несуществующий адрес).
Ответ `200`: `{"title": str, "team": str | null, "content": str}` (`team: null` — общий документ, `content` — markdown без шапки).
`404 {"detail": "Документ не найден или недоступен"}` — нет такого названия **или документ чужой команды** (правило то же, что у
поиска; факт существования не раскрываем). Без `X-User-Id` — `401`. При внедрении — ссылка на страницу Confluence с её правами.

## GET /actions
Действия текущего пользователя, новые сверху: `200 {"actions": [<Action>, ...]}`. Чужие не видны.

## POST /actions/{id}/confirm
Выполнить черновик. Права проверяются повторно.
- `200 <Action>` со статусом `done` или `failed`;
- `404` — нет такого действия **или оно чужое** (факт существования чужих действий не раскрывается);
- `409` — действие уже не `pending` (в том числе его прямо сейчас выполняет другое подтверждение);
- `403` — права на действие отозваны.

## POST /actions/{id}/cancel
Отменить черновик: `200 <Action>` со статусом `cancelled`; `404` / `409` — как у confirm.

---

# Онбординг: план, заявки, напоминания (спека 101, задача T4)
Тонкий слой над имитациями сервисов `backend/app/mcp_server` — права проверяют сами сервисы.
Модели (`Plan`, `PlanItem`, `AccessRequest`, `Reminder`, `SkillProfile`) — как в
`docs/specs/101-plan-next-step/plan.md`, раздел 3.1. Демо-данные, не регламент Авито.

**Ошибки (все эндпоинты раздела):** `404 {"detail":"Не найдено"}` — нет объекта **или нет доступа**
(факт существования чужих данных не раскрывается); `403` — объект виден, но действие запрещено
(стажёр отмечает пункт наставника, стажёр одобряет заявку); `409` — неверный переход статуса или
повторная заявка; `422` — неверные данные (`detail` — список ошибок).

Параметр `intern_id` (query) необязателен: по умолчанию — сам пользователь.

| Метод и путь | Кто | Ответ |
|---|---|---|
| `GET /interns` | все | `{"interns":[{"id","name","team"}]}` — чьи планы можно открыть (HR BP — пусто) |
| `GET /plan?intern_id=` | стажёр — свой, наставник — своих, руководитель — своих, куратор — всех | `Plan` |
| `POST /plan/items/{id}/status` `{"status":"done"\|"in_progress","reason"?}` | ответственный за пункт; наставник возвращает пункт стажёра с `reason` | `PlanItem` |
| `GET /plan/summary?intern_id=&week=1` | те же, кто видит план | `{"intern_id","week","closed":[…],"access_granted":[…],"carry_over":[PlanItem]}` |
| `GET /access/resources` | стажёр | `{"resources":[AccessResource]}` |
| `GET /access/requests?intern_id=` | стажёр — свои, наставник — своих | `{"requests":[AccessRequest + "resource_title"]}`, новые сверху |
| `POST /access/requests/{id}/decide` `{"approve":true\|false,"reason"?}` | только назначенный согласующий; при отказе `reason` обязателен | `AccessRequest` |
| `GET /profile/skills?intern_id=` | стажёр — свой, наставник — своих | `SkillProfile` |
| `POST /profile/skills` `{"intern_id","topic","level":"novice\|familiar\|confident"}` | только наставник этого стажёра (стажёр — `403`, чужие — `404`) | `SkillProfile`; событие `skill_level_changed` (спека 104) |
| `GET /reminders` | все | `{"reminders":[Reminder]}` — только активные свои |
| `POST /reminders/{id}/snooze` `{"days":1}` / `POST /reminders/{id}/done` | владелец | `Reminder` |
| `POST /demo/next-day` `{"intern_id"?}` | любая роль (демо-панель) | `{"days":{"intern-anya":3,…}}`; запускает проверку напоминаний |
| `POST /demo/reset` | любая роль (демо-панель) | `{"status":"reset"}` — стартовое состояние |

**Код-слово демо-кнопок.** Если на сервере задана переменная `DEMO_KEY` (публичный сайт), оба `/demo/*` требуют
заголовок `X-Demo-Key` = `encodeURIComponent(код-слово)`; без него или с неверным — `403 {"detail":"Нужно код-слово демо"}`,
данные не меняются. Интерфейс спрашивает код-слово один раз и хранит его до закрытия вкладки. `DEMO_KEY` пустой
(локально, Docker у эксперта) — заголовок не нужен.

Кнопки, которые нажимает человек («Готово», «Одобрить»), выполняются сразу — это и есть решение человека.

## POST /actions — черновик по кнопке («Сделать за меня»)
Запрос: `{"tool":"create_access_request","params":{"resource_id":"jira","level":"read","justification":"…"}}`.
Ответ `201 <Action>` со статусом `pending` — та же карточка, что от агента; выполнить — `POST /actions/{id}/confirm`.
`404` — нет такого write-инструмента или объекта (например, ресурс чужой команды: черновик не создаётся и название не
раскрывается); `403` — нет прав; `422` — неверные `params`.
Если сервис отказал при подтверждении (например, заявка на ресурс уже есть) — `Action.status = "failed"`, текст в `error`.

## Инструменты агента (`backend/app/agent/onboarding_tools.py`)
| Инструмент | read/write | Право | Кому показан |
|---|---|---|---|
| `get_plan` | read | `plan:read` | стажёр, наставник, руководитель, куратор |
| `set_plan_item_status` | write | `plan:write` | стажёр, наставник, руководитель |
| `list_access_resources` | read | `access:request` | стажёр |
| `create_access_request` | write | `access:request` | стажёр |
| `list_access_requests` | read | `access:read` | стажёр, наставник |
| `decide_access_request` | write | `access:approve` | наставник |
| `get_skill_profile` | read | `skills:read` | стажёр, наставник |

`set_skill_level` намеренно не инструмент: уровень навыка меняет только наставник, ИИ человека не оценивает.
Стажёру в системный промпт добавляется сводка: день, следующий шаг, кого ждём, уровень по темам.

## События и метрики (спека 302)
- `POST /chat` → дополнительно `"answer_id": "ans_…"` — для оценки ответа.
- `POST /plan/items/{id}/explained?intern_id=` `{"kind": "explain" | "steps" | "who"}` (по умолчанию `explain`) →
  `201 {"answer_id": "ans_…", "text": "…", "source": {"title": "…", "url": "…"} | null, "chips": ["…"]}`.
  Без модели (`scenario`/`echo`) ответ строит сервер (`app/agent/explain.py`): `explain` — раздел документа пункта
  под уровень стажёра, `steps` — предложения этого раздела по шагам, `who` — наставник/ответственный и раздел
  документа «К кому идти». Ничего не выдумывает: нет документа — так и говорит. `chips` — подсказки, которые интерфейс
  показывает кнопками, привязанными к пункту. Ответ записывается в события (инструмент `explain_item`), его можно
  оценить. Кто видит план — тот может; чужой или несуществующий пункт — `404`; неизвестный `kind` — `422`.
- `POST /feedback` `{"answer_id":"ans_…","useful":true}` → `204`. Только свой ответ; чужой или несуществующий — `404`.
- `GET /metrics?intern_id=` (наставник — свои стажёры, руководитель — команда, куратор — все; остальным `404`) →
```json
{ "interns": ["intern-anya"], "questions": 5, "closed_without_human": 2, "with_source_share": 0.4,
  "refused": 1, "drafts": 1, "avg_latency_ms": 820, "feedback": {"useful": 1, "not_useful": 0},
  "topics": [{"topic": "plan", "title": "план", "count": 2}],
  "unanswered_topics": [{"topic": "environment", "title": "окружение и запуск", "count": 1}],
  "conflict_topics": [{"topic": "git", "title": "git и ревью", "count": 1}] }
```
Только темы и количество — тексты вопросов не сохраняются. `conflict_topics` — темы, где документы противоречили
друг другу (SPEC 3.7): ответ начинается с «Документы расходятся», показывает оба варианта и в «закрыто без человека»
не входит.

---

# Персональный план, предложения по уровню, сравнение, отгул (SPEC 3.1, 3.6, 3.8, 4, 5 — правка 11.11)
**Статус: контракт согласуется** — эндпоинты ниже ещё не реализованы. Интерфейс сначала делается на поддельном
сервере по этому описанию, затем подключается к настоящему API. Сервисные функции под ними — у Codex (`.ai/HANDOFF.md`,
запись 11.11 «чекпоинт 1»). Ошибки — как в разделе «Онбординг»: `404` — нет объекта **или нет доступа**, `403` — объект
виден, действие запрещено, `409` — неверный переход или повтор, `422` — неверные данные.

Новые демо-пользователи (стажёры): `intern-kirill` — Кирилл, «Платформа объявлений», наставник `mentor-petr`;
`intern-liza` — Лиза, «Авито Доставка», наставник `mentor-maria`. Нужны для экрана сравнения: у каждого наставника два стажёра.

## PlanItem — новые поля
```json
{ "id": "anya.p.git", "kind": "personal", "reason": "в карте навыков Git — новичок",
  "skill_level": "novice", "known_marked": false, "catalog_key": "platform.git" }
```
(плюс все прежние поля пункта)

| Поле | Тип | Смысл |
|---|---|---|
| `kind` | `"common"` \| `"personal"` | общий пункт («для всех», у всех стажёров команды одинаковый) или персональный («для тебя», из каталога) |
| `reason` | `string \| null` | подпись «почему» — только у `personal`: «в карте навыков Git — новичок» или «добавил наставник» |
| `skill_level` | `"novice"` \| `"familiar"` \| `"confident"` \| `null` | уровень стажёра в теме пункта (`topic`); `null`, если темы нет. `confident` у общего пункта → метка «ты это умеешь — коротко» и сжатое объяснение |
| `known_marked` | `bool` | стажёр отметил «это я уже знаю» (пункт при этом не закрыт) |
| `catalog_key` | `string \| null` | ключ записи каталога — только у `personal` |

Снятые персональные пункты (уровень вырос, наставник убрал) в `Plan` не возвращаются; закрытые (`done`) остаются.
Общие пункты не снимаются никогда. Старый клиент, не знающий новых полей, продолжает работать.

## Задание на практике с проверкой (спека 107)
- `GET /plan` — у каждого пункта поле `practice_check: bool`: у задания есть проверка (кнопка «Сдать задание»).
- `POST /plan/items/{id}/practice` `{"answer": "1–2000 символов"}` — только стажёр, свой пункт с проверкой
  (иначе `404`, неотличимо) → `200`:
```json
{ "passed": false, "found": ["своя ветка под задачу"], "missing": ["как изменения попадают на сервер?"],
  "text": "Почти. Подумай: …", "source": {"title": "Учебный репозиторий — клонирование и ветки", "url": "…"},
  "item_id": "<id пункта>", "topic": "git" }
```
Без модели; текст ответа не сохраняется, в события — `practice_checked` с `passed`.

## Каталог и правка персональных пунктов (наставник)
| Метод и путь | Кто | Ответ |
|---|---|---|
| `GET /plan/catalog?intern_id=` | наставник этого стажёра | `{"items":[CatalogItem]}` — каталог команды стажёра; у каждого `in_plan: bool` |
| `POST /plan/items` `{"intern_id","catalog_key"}` | наставник этого стажёра | `201 PlanItem` (`kind: "personal"`, `reason: "добавил наставник"`); ключ чужой команды — `404`; уже в плане — `409` |
| `DELETE /plan/items/{id}?intern_id=` | наставник этого стажёра | `204`; общий пункт — `403`; закрытый — `409` |
| `POST /plan/items/{id}/known` `{"known": true\|false}` | стажёр, свой пункт с темой | `PlanItem`; может создать предложение по уровню (ниже). Пункт без темы — `422` |

```json
{ "key": "platform.git", "team": "Платформа объявлений", "topic": "git", "topic_title": "Git",
  "level": "novice", "title": "Пройти практикум по веткам и pull request", "summary": "…",
  "doc_source_id": "demo:15-…", "stage": "week1", "in_plan": true }
```
(`CatalogItem`.) Стажёр, руководитель, куратор, HR BP: `404` на эндпоинты наставника. События:
`personal_item_added` / `personal_item_removed` (payload без текстов).

## «Память»: вопрос наставнику → база знаний команды (PR #45 Codex + Claude 13.11)
Сервис — `app/mcp_server/mentor_inbox.py`. Нажатие кнопки человеком — его подтверждение (черновик сервиса создаётся и подтверждается в одном запросе).

- `GET /mentor/questions` → `{"questions": [MentorQuestion]}`. Стажёр — свои, наставник — вопросы своих стажёров; остальным ролям `404`. Без ответа — сверху.
- `POST /mentor/questions` `{"text": str (1–3000)}` → `201 MentorQuestion` — только стажёр (`404` остальным). Наставник сразу получает уведомление `kind: "mentor_question"`, кнопка «Ответить».
- `POST /mentor/questions/{id}/answer` `{"text": str (1–6000), "publish": bool = true}` → `MentorQuestion`. Только наставник этого стажёра (`404` остальным), повтор — `409`. `publish: true` — обезличенный ответ (`public_content`: имена и контакты заменены метками) добавляется в базу знаний команды как документ «Ответ наставника, ДД.ММ.ГГГГ»; бот и поиск находят его только для этой команды. Стажёр получает уведомление `kind: "mentor_answer"` (факт, «Открыть»).
- `POST /mentor/questions/{id}/publish` → `MentorQuestion` — добавить в базу уже данный ответ; повтор — `409`.

`MentorQuestion`: `{"id", "intern_id", "intern_name", "mentor_id", "team", "question", "created_day", "status": "pending"|"answered", "answer": str|null, "answered_day", "answered_at", "publication_status": "not_requested"|"pending"|"published", "public_content": str|null, "source_id"}`.
Новые значения: `Reminder.kind` — `mentor_question`, `mentor_answer`; `Reminder.action.target` — `mentor_question` (блок «Вопросы наставнику»). `GET /documents?title=Ответ наставника, …` — опубликованный ответ своей команды.

## Предложения по уровню (SPEC 4)
Бот **предлагает**, наставник **решает**. Стажёр предложений не видит — ни до решения, ни после отказа; он видит
только результат (новый уровень в `/profile/skills` и уведомление).

| Метод и путь | Кто | Ответ |
|---|---|---|
| `GET /skills/suggestions?intern_id=&status=pending` | наставник — своих стажёров (без `intern_id` — всех своих) | `{"suggestions":[SkillSuggestion]}`, новые сверху. Остальным ролям, включая стажёра, — `404` |
| `POST /skills/suggestions/{id}/decide` `{"accept": true\|false}` | наставник этого стажёра | `SkillSuggestion`. `accept: true` меняет уровень как `POST /profile/skills` и пересобирает персональные пункты; уже решено — `409` |

```json
{ "id": "sug_…", "intern_id": "intern-anya", "intern_name": "Аня Смирнова", "topic": "git",
  "topic_title": "Git", "from_level": "novice", "to_level": "familiar",
  "basis": "закрыла 2 пункта по Git", "created_day": 4,
  "status": "pending", "decided_day": null }
```
(`SkillSuggestion`; `status`: `pending` | `accepted` | `dismissed`.) Поводы: закрыто ≥ 2 пунктов по теме или «это я уже
знаю». Не больше одного `pending` на пару стажёр + тема. Смена уровня и решение по предложению — **не инструменты
агента**: решает только человек кнопкой.

## Сравнение двух стажёров (SPEC 5)
`GET /plan/compare?intern_ids=intern-anya,intern-kirill` — только наставник, ровно два **своих** стажёра (чужой —
`404`; не два id — `422`). Это не рейтинг: без процентов и сортировки по успехам.
```json
{ "interns": [ {"id": "intern-anya", "name": "Аня Смирнова"}, {"id": "intern-kirill", "name": "Кирилл …"} ],
  "common": [ { "key": "w1.access-base", "title": "Запросить базовые доступы", "stage": "week1", "topic": null,
                "by_intern": { "intern-anya": {"status": "done", "skill_level": null},
                               "intern-kirill": {"status": "in_progress", "skill_level": null} } } ],
  "personal": { "intern-anya": [ "<PlanItem>" ], "intern-kirill": [ "<PlanItem>" ] } }
```
`common` — общие пункты, сопоставленные по `key` (часть id после имени стажёра); `personal` — персональные пункты
каждого с `reason`.

## Отгул на один день (SPEC 3.8; сервис — PR #46, `backend/app/mcp_server/ABSENCE.md`)
Причина — только закрытый список: `personal` (личные дела), `family` (семейные дела), `study` (учебные дела).
Свободного текста и медицинских полей нет. Решает **руководитель** стажёра; наставник видит только факт.

| Метод и путь | Кто | Ответ |
|---|---|---|
| `POST /actions` `{"tool":"create_absence_request","params":{"day":"2026-11-14","reason":"personal"}}` | стажёр | `201 <Action>` (`pending`) — та же карточка черновика; `confirm` создаёт заявку `pending` у руководителя. День раньше текущего дня стажировки или уже есть заявка на этот день — `Action.status = "failed"`, текст в `error` |
| `GET /absence/requests` | стажёр — свои; руководитель — своей команды | `{"requests":[AbsenceRequest]}`, новые сверху; остальным — `404` |
| `POST /absence/requests/{id}/decide` `{"approve": true\|false}` | только назначенный руководитель | `AbsenceRequest`; уже решено — `409`. Кнопка руководителя и есть решение человека |
| `GET /absence/facts?intern_id=` | наставник своего стажёра | `{"facts":[{"intern_id","day"}]}` — только согласованные, без причины и id заявки |

```json
{ "id": "ABS-…", "intern_id": "intern-anya", "intern_name": "Аня Смирнова", "lead_id": "lead-olga",
  "day": "2026-11-14", "reason": "personal", "reason_title": "Личные дела",
  "status": "pending", "created_day": 4, "decided_day": null }
```
(`AbsenceRequest`; `status`: `pending` | `approved` | `rejected`. После `rejected` на тот же день можно подать снова.)

Агент: при намерении «отгул» («мне завтра к врачу», «как отпроситься») отвечает по регламенту с источником и
возвращает в `actions` черновик `create_absence_request` (день — по фразе, по умолчанию завтра; причина — `personal`).
Подтверждает только человек. Больничный и отпуск — к HR BP, черновик не создаётся.
Инструменты агента: `create_absence_request` (write, право `absence:request`, стажёр), `list_absence_requests`
(read, `absence:read`, стажёр и руководитель). Решение руководителя — не инструмент.

## Напоминания и уведомления — новые типы (SPEC 3.6)
`Reminder` получает поля `kind`, `action` и необязательные ссылки:
```json
{ "id": "rem_…", "user_id": "intern-anya", "kind": "skill_changed",
  "text": "Наставник отметил: Git — уверенно. План обновился",
  "action": { "label": "Открыть план", "target": "plan" },
  "plan_item_id": null, "request_id": null, "suggestion_id": null, "absence_request_id": null,
  "status": "active", "created_day": 4, "snooze_until_day": null }
```
| `kind` | Кому | Повод | `action.target` |
|---|---|---|---|
| `plan_item` | стажёр | пункт просрочен (было) | `plan_item` |
| `access_request` | стажёр | заявка на доступ ждёт ≥ 2 дней (было) | `access_request` |
| `skill_changed` | стажёр | наставник изменил уровень (сам или по предложению) | `plan` |
| `personal_item_added` | стажёр | в план добавлен персональный пункт | `plan_item` |
| `absence_pending` | стажёр | заявка на отгул ждёт решения ≥ 2 дней — «напомнить руководителю?» | `absence_request` |
| `absence_decided` | стажёр | отгул согласован / отклонён | `absence_request` |
| `absence_today` | стажёр | сегодня отгул, сроки сдвинуты | `plan` |
| `skill_suggestion` | наставник | бот предлагает поднять уровень | `skill_suggestion` |
| `absence_fact` | наставник | согласован отгул стажёра (только дата) | `intern` |
| `absence_new` | руководитель | новая заявка на отгул | `absence_request` |

Старые напоминания без `kind` считаются `plan_item` или `access_request` по заполненной ссылке. Одно активное
напоминание на один повод. `GET /reminders`, `snooze`, `done` — без изменений; наставник и руководитель получают свои
через тот же `GET /reminders`. Отклонённое предложение по уровню стажёру уведомлением не приходит.

