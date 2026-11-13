# 106 — Отгул на один день: план реализации

## 1. Подход
Сервис отсутствий — имитация в `app/mcp_server/absence.py` с тем же механизмом черновиков, что у заявок на доступ:
агент создаёт черновик, человек подтверждает, сервис при подтверждении ещё раз проверяет день, руководителя и команду.
Причина — закрытый список (`AbsenceReason`), свободного текста нет — так медицинские данные не попадают в систему.
Сценарный режим узнаёт отгул по словам (`ABSENCE_WORDS`) и разбирает дату (`_absence_day`); с моделью — тот же
инструмент, а правило регламента агент добавляет сам (`absence_rule`).

## 2. Что меняется
| Часть | Файлы / модули | Чья зона |
|---|---|---|
| Имитации сервисов | `backend/app/mcp_server/absence.py`, `absence_models.py`, `seed/absence.json`, `ABSENCE.md` | Codex (#46) |
| База | `supabase/migrations/…absence…` (RLS) | Codex |
| Агент | `backend/app/agent/onboarding_tools.py` (`create_absence_request`, `intern_today`), `service.py` (`absence_rule`) | Claude (#72) |
| Сценарный режим | `backend/app/llm/scenario_provider.py` (`ABSENCE_WORDS`, `_absence_day`, `_reason`) | Claude (#72) |
| HTTP | `backend/app/onboarding_api.py`: `/absence/requests`, `/absence/requests/{id}/decide`, `/absence/facts` | Claude (#72) |
| Интерфейс | `frontend/src/components/AbsencePanel.tsx`, карточка черновика в `ChatPanel.tsx` | Claude (#72) |
| Документ | `backend/app/rag/demo_docs/14-day-off.md` | Codex |

## 3. Данные и контракты
См. `docs/API.md`, раздел «Отгул». `AbsenceRequest {id, intern_id, intern_name, lead_id, day, reason, reason_title,
status: pending|approved|rejected, created_day, decided_day}`; наставнику — `{intern_id, day}`.

## 4. Проверка
Сервисные тесты (память, PostgreSQL, RLS), HTTP и чат, интерфейс, золотой набор (`act-05…08`, `live-03…05`). Вживую —
шаги 4, 6, 7 маршрута README.

## 5. Риски и запасной вариант
Сдвиг сроков в день отгула — «режем вторым» (SPEC §13). Успели.

## 6. Что заменяется при внедрении в Авито
Сервис отсутствий — кадровая система Авито через MCP; руководитель — из оргструктуры. Агент и интерфейс не меняются.
