# 101 — План стажёра, статусы и следующий шаг: задачи

Одна задача — один PR. Отмечаем `[x]`, когда PR слит. `[P]` — можно делать параллельно.

| № | Задача | Кто | Закрывает критерии | PR |
|---|---|---|---|---|
| T1 | Имитации сервисов: модели, сервисы checklist/access/hiring/clock/events, `InMemoryStore`, seed, тесты — реализовано, на ревью | Codex | AC-1…AC-11 (логика; перезапуск AC-5 — T3) | [#17](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/17) |
| T2 | [P] Макет экрана «план + чат» на тестовых данных в форме контракта 3.1 | Claude | AC-1, AC-2 (вид) | |
| T3 | `PostgresStore` + миграция + авто-seed в Docker | Codex | AC-5 (после перезапуска) | |
| T4 | [API] HTTP `/plan`, `/requests`, `/reminders`, `/demo/*` + инструменты агента + подключение фронта к API | Claude | AC-1…AC-11 (сквозные) | |
| T5 | MCP-обёртка над функциями сервисов (пакет `mcp`) + тест вызова по протоколу | Codex | — (ТЗ: действия через MCP) | |

- [ ] T1 — **реализовано, на ревью [PR #17](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/17)**: `backend/app/mcp_server/` по `plan.md` 3.1–3.4, тесты `backend/tests/mcp/`; чекбокс отмечается после мержа PR по правилу выше.
- [x] T2 — Claude: `frontend/`, данные-заглушки повторяют модели `Plan`, `AccessRequest`, `Reminder`. Ветка `claude/plan-screen`.
- [ ] T3 — Codex: после T1.
- [ ] T4 — Claude: после T1. Разбита на две части: T4a — API и инструменты агента `[API]` (ветка `claude/api-onboarding`); T4b — интерфейс на API (TanStack Query, Zod), ветка `claude/frontend-api`.
- [ ] T5 — Codex: после T1, параллельно с T3 не трогает те же файлы.

Готово, когда: все критерии приёмки из `spec.md` закрыты автотестами (таблица «Трассировка»), статус спецификации — `реализована`.
