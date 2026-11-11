# 102 — План реализации

- Интерфейс: `frontend/src/lib/chat.ts` — `explainScripted(item, profile)` (сценарный ответ, словарь `DEPTH`),
  `explainQuestion(item)` (вопрос модели); подсказка уровня — `PlanRow` в `frontend/src/components/PlanPanel.tsx`.
- Агент: `backend/app/agent/prompts.py` (правила глубины), `plan_context()` в `backend/app/agent/onboarding_tools.py`
  добавляет «Уровень по темам» в системный промпт стажёра.
- Данные: темы, задания и документы пунктов — seed `backend/app/mcp_server/seed/onboarding.json` (Codex, 101-T1).
- Решение: в сценарном режиме не зовём backend за объяснением — всё нужное уже есть в плане и карте, ответ мгновенный.
