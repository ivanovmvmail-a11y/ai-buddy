# 101 — План стажёра, статусы и следующий шаг: задачи

Одна задача — один PR. Отмечаем `[x]`, когда PR слит. `[P]` — можно делать параллельно.

| № | Задача | Кто | Закрывает критерии | PR |
|---|---|---|---|---|
| T1 | Имитации сервисов: модели, сервисы checklist/access/hiring/clock/events, `InMemoryStore`, seed, тесты — слито | Codex | AC-1…AC-11 (логика) | [#17](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/17) |
| T2 | [P] Макет экрана «план + чат» на тестовых данных в форме контракта 3.1 | Claude | AC-1, AC-2 (вид) | #16 |
| T3 | `PostgresStore` + миграция + авто-seed в Docker + оптимизация чтения — слито | Codex | AC-5 (после перезапуска), общий набор тестов на двух хранилищах | [#21](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/21) |
| T4 | [API] HTTP `/plan`, `/requests`, `/reminders`, `/demo/*` + инструменты агента + подключение фронта к API — слито | Claude | AC-1…AC-11 (сквозные) | #19, #20 |
| T5 | MCP-обёртка над функциями сервисов (официальный `mcp`/FastMCP, stdio) + тесты memory/stdio — слито | Codex | — (ТЗ: действия через MCP) | [#34](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/34) |

- [x] T1 — слито: [PR #17](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/17), логика и имитации сервисов.
- [x] T2 — Claude: `frontend/`, данные-заглушки повторяют модели `Plan`, `AccessRequest`, `Reminder`. Ветка `claude/plan-screen`.
- [x] T3 — слито: [PR #21](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/21). AC-5 проверяется разными процессами на PostgreSQL.
- [x] T4 — слито: #19 (T4a), #20 (T4b). Разбита на две части: T4a — API и инструменты агента `[API]` (ветка `claude/api-onboarding`); T4b — интерфейс на API (TanStack Query, Zod), ветка `claude/frontend-api`.
- [x] T5 — слито: [PR #34](https://github.com/ivanovmvmail-a11y/ai-buddy/pull/34). Восемь инструментов, явный user_id, память/stdio проверены официальным клиентом.

Готово, когда: все критерии приёмки из `spec.md` закрыты автотестами (таблица «Трассировка»), статус спецификации — `реализована`.
