# STATUS — общая доска задач

Обновляй свою строку при старте задачи и перед PR. Статусы: `todo` · `в работе` · `на ревью` · `готово` · `блок`.

| # | Задача | Владелец | Ветка | Статус | PR | Заметки |
|---|---|---|---|---|---|---|
| 1 | Каркас проекта (backend + frontend + правила) | Claude | main (init) | готово | — | стартовый коммит |
| 2 | Спецификация по ТЗ → docs/SPEC.md | Claude | claude/spec | готово | #14 | интервью проведено 10.11; один глубокий сценарий «Первые недели и чек-лист» + профиль стажёра |
| 3 | Деплой Vercel + Render + UptimeRobot (бонус к Docker) | Claude + Миша | claude/deploy | todo | | проверить GigaChat с Render |
| 4 | Backend FastAPI → Flask + первые тесты | Claude | claude/flask | готово | #7 | по ТЗ: стек Авито Go / Python+Flask |
| 5 | Docker: запуск одной командой | Claude | claude/docker | готово | #8 | Docker и тесты проверяет CI на GitHub (локально нет SVM в BIOS) |
| 6 | Инструменты агента: права + черновик→подтверждение [API] | Claude | claude/agent-tools | готово | #9 | |
| 7 | Шаблон SDD-спецификаций + 001-agent-tools | Claude | claude/sdd-template | готово | #10 | |
| 8 | Страховочные правки по отзыву жюри [API] | Claude | claude/safety-fixes | готово | #11 | |
| 9 | RAG: загрузка документов и поиск с изоляцией команд | Codex | codex/rag-basic | готово | [#12](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/12) | Пункты 1–7 ревью исправлены; 117 офлайн + 4 PostgreSQL-теста, покрытие 98,97% |
| 10 | Эмбеддер GigaChat (по выбору) + Windows-цикл + авто-загрузка документов в Docker; миграция RAG в Supabase | Claude | claude/gigachat-embeddings | готово | #13 | эмбеддинги GigaChat на бесплатном тарифе — 402, по умолчанию поиск по словам |
| 11 | Спека 101 (план, статусы, следующий шаг) + контракт имитаций сервисов для Codex | Claude | claude/spec-101-plan | готово | #15 | задачи T1–T5 в docs/specs/101-plan-next-step/tasks.md |
| 12 | 101-T1: имитации сервисов (чек-лист, доступы, найм, часы, события) в памяти + seed + тесты | Codex | codex/mcp-services | на ревью | [#17](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/17) | Ревью 1–5, 7–9 исправлено, 6 → T3; 281 passed, покрытие 98,82% |
| 13 | 101-T2: макет экрана «план + чат» на тестовых данных | Claude | claude/plan-screen | на ревью | | Vitest 24 теста, покрытие 99%; данные пока в браузере, API — в T4 |

## Блокеры
_нет_
