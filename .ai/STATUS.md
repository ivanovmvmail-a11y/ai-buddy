# STATUS — общая доска задач

Обновляй свою строку при старте задачи и перед PR. Статусы: `todo` · `в работе` · `на ревью` · `готово` · `блок`.

| # | Задача | Владелец | Ветка | Статус | PR | Заметки |
|---|---|---|---|---|---|---|
| 1 | Каркас проекта (backend + frontend + правила) | Claude | main (init) | готово | — | стартовый коммит |
| 2 | Спецификация по ТЗ → docs/SPEC.md | Claude | claude/spec | готово | #14 | интервью проведено 10.11; один глубокий сценарий «Первые недели и чек-лист» + профиль стажёра |
| 3 | Деплой: сайт и backend на Railway (Render/Vercel/Netlify не работают из РФ) (бонус к Docker) | Claude + Миша | claude/deploy | готово | #29–#32 | Проверено в браузере: план грузится, чат отвечает через GigaChat, база Supabase |
| 4 | Backend FastAPI → Flask + первые тесты | Claude | claude/flask | готово | #7 | по ТЗ: стек Авито Go / Python+Flask |
| 5 | Docker: запуск одной командой | Claude | claude/docker | готово | #8 | Docker и тесты проверяет CI на GitHub (локально нет SVM в BIOS) |
| 6 | Инструменты агента: права + черновик→подтверждение [API] | Claude | claude/agent-tools | готово | #9 | |
| 7 | Шаблон SDD-спецификаций + 001-agent-tools | Claude | claude/sdd-template | готово | #10 | |
| 8 | Страховочные правки по отзыву жюри [API] | Claude | claude/safety-fixes | готово | #11 | |
| 9 | RAG: загрузка документов и поиск с изоляцией команд | Codex | codex/rag-basic | готово | [#12](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/12) | Пункты 1–7 ревью исправлены; 117 офлайн + 4 PostgreSQL-теста, покрытие 98,97% |
| 10 | Эмбеддер GigaChat (по выбору) + Windows-цикл + авто-загрузка документов в Docker; миграция RAG в Supabase | Claude | claude/gigachat-embeddings | готово | #13 | эмбеддинги GigaChat на бесплатном тарифе — 402, по умолчанию поиск по словам |
| 11 | Спека 101 (план, статусы, следующий шаг) + контракт имитаций сервисов для Codex | Claude | claude/spec-101-plan | готово | #15 | задачи T1–T5 в docs/specs/101-plan-next-step/tasks.md |
| 12 | 101-T1: имитации сервисов (чек-лист, доступы, найм, часы, события) в памяти + seed + тесты | Codex | codex/mcp-services | готово | [#17](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/17) | Слито; отложенный пункт 6 реализован в T3 |
| 13 | 101-T2: макет экрана «план + чат» на тестовых данных | Claude | claude/plan-screen | готово | #16 | Vitest 24 теста, покрытие 99%; данные пока в браузере, API — в T4 |
| 14 | 101-T4a [API]: HTTP онбординга + инструменты агента поверх имитаций сервисов | Claude | claude/api-onboarding | готово | #19 | 318 тестов, покрытие 99%; проверено вживую с GigaChat |
| 15 | 101-T4b: интерфейс на API (TanStack Query, Zod) + resource_title в заявках [API] | Claude | claude/frontend-api | готово | #20 | 28 тестов Vitest на поддельном сервере, покрытие 99%; проверено вживую |
| 16 | 101-T3: PostgreSQL-хранилище онбординга, миграция, seed и оптимизация чтения | Codex | codex/onboarding-postgres | готово | [#21](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/21) | Ревью 1–4, 8 исправлено; 5–7 → HANDOFF; PostgreSQL: 507 passed / 98,32%; офлайн: 336 passed / 93,47% |
| 17 | Спека 003: сценарный режим без ключа (LLM_PROVIDER=scenario по умолчанию) | Claude | claude/scenario-mode | готово | #22 | 337 тестов backend; проверено на демо-документах |
| 18 | Спека 201: экран наставника — карточки стажёров, что зависло, итоги недели | Claude | claude/mentor-screen | готово | #23 | после #22; 34 теста Vitest |
| 19 | Спека 004: золотой набор (37 вопросов) + отчёты; промпт против выдумок | Claude | claude/golden-set | готово | #24 | сценарный 37/37, GigaChat 36/37 (отчёт docs/golden-report-gigachat.md), утечек 0 |
| 20 | Спека 302 [API]: события чата, «полезно / не полезно», /metrics, частые темы у наставника | Claude | claude/events-metrics | готово | #25 | после #24; backend +22 теста, frontend 39 |
| 21 | Проверка «как у эксперта» в Docker: сценарный режим по умолчанию, честные источники | Claude | claude/docker-expert-check | готово | | весь маршрут SPEC 14 пройден в чистой копии без ключей |
| 22 | Спека 104 [API]: наставник меняет уровень навыка стажёра (HTTP + экран наставника) | Claude | claude/skill-profile | готово | #35 | |
| 23 | Спеки 102 (объяснение под уровень) и 301 (напоминания) — оформить по готовому коду | Claude | claude/specs-102-301 | готово | #36 | только документы; найдено отличие от SPEC: нет колокольчика (301-T4) |
| 24 | Колокольчик напоминаний в шапке (301-T4) + ревью PR #34 Codex | Claude | claude/reminders-bell | готово | #37 | |
| 25 | Спека 103 (заявка на доступ) по готовому коду; 301-T4 отмечена | Claude | claude/spec-103-presentation | готово | #38 | только документы |
| 26 | 101-T5: MCP-протокол поверх имитаций сервисов | Codex | codex/mcp-protocol | готово | [#34](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/34) | Ревью 1–7 исправлено; один пользователь на запуск; extra mcp: 415 passed / 94,24%; PostgreSQL: 608 / 98,23% |
| 27 | Grafana: готовая панель метрик из PostgreSQL | Codex | codex/grafana-demo | готово | [#39](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/39) | Docker проверен; PostgreSQL: 612 passed / 98,23%; read-only datasource |
| 28 | Закрыть пул PostgreSQL в RAG CLI | Codex | codex/rag-cli-close | готово | [#40](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/40) | --rag-postgres: 425 passed / 94,26%; успех/ошибки закрывают пул |
| 29 | Общий пул PostgreSQL для RAG и онбординга | Codex | codex/shared-postgres-pool | готово | [#41](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/41) | Оба PostgreSQL-флага: 620 passed / 98,14%; до 8 соединений суммарно |
| 30 | Grafana: закрыть public-представления для API-ролей Supabase | Codex | codex/grafana-view-permissions | готово | [#42](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/42) | Default grants anon/authenticated закрыты; 634 passed / 98,15%; Docker проверен; миграции #39 и #42 применены к Supabase (Claude) |
| 31 | Прогон демо SPEC §14 с нуля + порядок в STATUS; «по ссылке ниже» без документа | Claude | claude/status-demo-run | готово | #43 | шаги 1–7 пройдены без ключа; шаг 8 (Grafana) — только в Docker/CI |
| 32 | [API] Сценарные объяснения пункта — в события и метрики | Claude | claude/scenario-explain-metrics | готово | #44 | без ключа «Объяснить» считается в /metrics и Grafana, можно оценить |
| 33 | Аудит 11.11, B2: маршрут проверки в README (шаги, кнопки), версии, порты, структура | Claude | claude/readme-expert-route | готово | #47 | шаги сверены в браузере без ключа |
| 34 | Аудит 11.11: D3 журнал сервера (LOG_LEVEL), D5 статусы спецификаций, очередь S2–S4 для Codex в HANDOFF | Claude | claude/audit-hardening | готово | #48 | 426 passed |
| 35 | [API] Аудит D6: код-слово для демо-кнопок на публичном сайте (DEMO_KEY) | Claude | claude/demo-key | готово | #49 | backend 428, frontend 49 / 98% |
| 36 | [API] Аудит S1+S7: без ключа объяснение, «по шагам», «к кому идти» — сервер по документу пункта; фразы «спасибо», «кто наставник», «что у Ани зависло» | Claude | claude/scenario-answers | готово | #51 | backend 452, frontend 51 / 98%, золотой 37/37 |
| 37 | Аудит S2: 9 документов «как сделать» (клонирование, ревью, красный пайплайн, песочница, локальный запуск, доступ); золотой набор 46 вопросов | Claude | claude/howto-docs | готово | #52 | сценарный 46/46; backend 452 |
| 38 | Аудит S6: страница «Мой профиль» стажёра (SPEC 4, 6) | Claude | claude/my-profile | готово | #53 | frontend 53 |
| 39 | Аудит S6: итоги недели стажёру в чате (SPEC 3.2) | Claude | claude/intern-weekly | готово | #54 | после #53; frontend 58 |
| 40 | [API] Аудит S6: противоречия в документах — оба варианта с источниками, сигнал наставнику (SPEC 3.7) | Claude | claude/doc-conflicts | готово | #55 | после #54; backend 455, золотой 48/48, frontend 58 |
| 41 | [API] Аудит S6/D1: хранилище действий — асинхронный протокол для PostgreSQL, атомарное подтверждение, «Сброс» очищает черновики | Claude | claude/action-store | готово | #56 | после #55; таблица — Codex (HANDOFF) |
| 42 | [API] Аудит S6/D7: переписка сохраняется (GET /chat/history), браузер помнит пользователя, черновики восстанавливаются | Claude | claude/chat-history | готово | #57 | backend 464, frontend 60; таблица — Codex (HANDOFF) |
| 43 | [API] Аудит D4, D8, мелочи: чужой ресурс — сразу 404, без заголовка — 401, лимиты сообщения, ошибки JSON, approve только bool | Claude | claude/api-hardening | готово | #58 | после #57; backend 468 |
| 44 | Аудит S5 + мелочи интерфейса: честный раздел про MCP в README, «Написать наставнику» по зависшей заявке, шапка на телефоне 203→91 px, точка «новое» на «Чат», скорость «быстрее 0,1 с» | Claude | claude/ui-polish | готово | #60 | после #58; frontend 63 |
| 45 | Аудит S4: повышенные доступы требуют решения наставника | Codex | codex/audit-s4-access-approval | готово | [#59](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/59) | 720 passed / 97,73%, PostgreSQL; мерж после комментария человека; бонусы #45/#46/#50 Draft |
| 46 | Аудит S3: реальные timestamps событий и календарные сутки Grafana | Codex | codex/audit-s3-event-time | готово | [#61](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/61) | 700 passed / 97,63%, PostgreSQL; 30 дней, timezone браузера; мерж после комментария человека |
| 47 | Аудит S2: загрузка how-to документов и изоляция команд | Codex | codex/audit-s2-howto-ingest | на ревью | [#62](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/62) | 698 passed / 97,63%, оба PostgreSQL-флага; 19 документов; мерж после комментария человека |
| 48 | Ревью Codex #59 (повторно), #61, #62; поддельный сервер фронта — новые документы пунктов, как в #62 | Claude | claude/mock-howto-links | на ревью | | frontend 64 |
| 49 | Чекпоинт 1: SPEC — персональный план, предложения по уровню, отгул, уведомления; записка Codex | Claude | claude/spec-adaptive-plan | готово | #64, #65 | только документы; [API]-контракт — отдельный PR claude/api-adaptive-plan |
| 50 | План: метки «для всех / для тебя», «почему», «ты это умеешь — коротко» (SPEC 3.1) | Claude | claude/plan-labels | готово | #66 | frontend 70; персональные пункты придут от сервера после каталога Codex |
| 51 | Экран наставника: «Бот предлагает поднять уровень» и сравнение двух планов (SPEC 4, 5) | Claude | claude/mentor-suggestions-compare | на ревью | | frontend 77; на поддельном сервере, на настоящем появится после Codex (п. 0–2 HANDOFF) |

| C1.01 | Чекпоинт 1, 0+1: seed и персональный план | Codex | codex/personal-plan-catalog | на ревью | [#67](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/67) | 791 passed / 97,75%; /health=200; DEMO_USERS добавляет Claude |
| C1.5 | Чекпоинт 1, 5: отгул и напоминания | Codex | codex/absence | на ревью | [#46](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/46) | 836 passed / 98,14%; main влит; уведомления и +1 день сроков |
| C1.2 | Чекпоинт 1, 2: предложения по уровню | Codex | codex/skill-suggestions | на ревью | [#68](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/68) | 828 passed / 97,85%; зависит от #67; решение только наставником |

## Блокеры
- нет (блокер #62 снят: текст документа 13 исправлен, #62 слит 11.11).
