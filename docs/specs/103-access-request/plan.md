# 103 — План реализации

- Сервис: `backend/app/mcp_server/access.py` (Codex, 101-T1/T3) — `list_resources`, `create_request`, `list_requests`,
  `decide_request`; смена статуса пункта и закрытие напоминаний — в той же транзакции.
- Черновик и подтверждение — общий механизм спеки 001 (`backend/app/agent/tools.py`): `kind="write"` →
  `Action(pending)` → `POST /actions/{id}/confirm`. Кнопка «Сделать за меня» — `POST /actions` (тот же черновик).
- Инструменты агента: `backend/app/agent/onboarding_tools.py`. HTTP: `backend/app/onboarding_api.py`.
- Интерфейс: `onDo` и `accessDraftParams` (`frontend/src/app/page.tsx`, `frontend/src/lib/chat.ts`), карточка черновика
  в `ChatPanel.tsx`, решение наставника в `PlanPanel.tsx`.
- Решения: уровень по умолчанию `read`; согласующий — поле ресурса; «Одобрить» наставника выполняется сразу —
  нажатие человека и есть решение (черновик нужен только для действий, которые готовит ИИ).
