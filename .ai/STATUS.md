# STATUS — общая доска задач

Обновляй свою строку при старте задачи и перед PR. Статусы: `todo` · `в работе` · `на ревью` · `готово` · `блок`.

| # | Задача | Владелец | Ветка | Статус | PR | Заметки |
|---|---|---|---|---|---|---|
| 1 | Каркас проекта (backend + frontend + правила) | Claude | main (init) | готово | — | стартовый коммит |
| 2 | Спецификация по ТЗ → docs/SPEC.md | Claude | claude/spec | готово | #14 | интервью проведено 10.11; один глубокий сценарий «Первые недели и чек-лист» + профиль стажёра |
| 3 | Деплой Vercel + Render + UptimeRobot (бонус к Docker) | Claude + Миша | claude/deploy | на ревью | #29 | render.yaml + PORT от Render; дальше Миша подключает аккаунты |
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
| 19 | Спека 004: золотой набор (37 вопросов) + отчёты; промпт против выдумок | Claude | claude/golden-set | готово | #24 | сценарный 37/37, GigaChat 37/37, утечек 0 |
| 20 | Спека 302 [API]: события чата, «полезно / не полезно», /metrics, частые темы у наставника | Claude | claude/events-metrics | готово | #25 | после #24; backend +22 теста, frontend 39 |
| 21 | Проверка «как у эксперта» в Docker: сценарный режим по умолчанию, честные источники | Claude | claude/docker-expert-check | на ревью | | весь маршрут SPEC 14 пройден в чистой копии без ключей |

## Блокеры
_нет_
