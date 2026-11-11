# 104 — План реализации

- Хранение и права уже есть: `app/mcp_server/hiring.py` (`get_skill_profile`, `set_skill_level`, Codex, 101-T1/T3).
- HTTP: `POST /profile/skills` в `app/onboarding_api.py` — тонкий слой, права проверяет `hiring.set_skill_level`.
- Интерфейс: `SkillLevels` в `frontend/src/components/InternCards.tsx`, вызов `api.setSkill`, после ответа обновляются
  все запросы (`useRefresh`), поэтому подсказки в плане стажёра меняются сразу.
- Агент не меняется: уровень уже попадает в промпт и в сценарный режим (`explainScripted`).
