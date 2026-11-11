# 301 — План реализации

- Сервис: `backend/app/mcp_server/clock.py` (Codex, 101-T1/T3) — `_tick` (правила крона), `advance_day`, `cron_tick`,
  `list_reminders`, `snooze_reminder`, `done_reminder`; закрытие напоминаний при закрытии пункта — `checklist.py`,
  при решении заявки — `access.py`.
- HTTP: `backend/app/onboarding_api.py` — `/reminders`, `/reminders/{id}/snooze|done`, `/demo/next-day`, `/demo/reset`.
- Интерфейс: `showReminders` в `frontend/src/app/page.tsx`, `reminderMsg` в `frontend/src/lib/chat.ts`, демо-панель.
- Решение: виртуальный день вместо часов сервера — воспроизводимое демо и тесты без ожидания.
