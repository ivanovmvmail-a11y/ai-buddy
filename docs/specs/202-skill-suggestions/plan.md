# 202 — Предложения по уровню: план реализации

## 1. Подход
Сервис «Найм» (`hiring.py`) при отметке «Это я уже знаю» или закрытии пункта темы проверяет повод (`_maybe_suggest`)
и создаёт одно открытое предложение на тему. Решение наставника идёт через тот же путь смены уровня, что и ручная
правка (`_set_level`), поэтому пересборка плана (спека 105) и уведомление стажёру (спека 303) работают одинаково.
Отказ стажёру не показывается — уведомление о результате создаётся только при принятии.

## 2. Что меняется
| Часть | Файлы / модули | Чья зона |
|---|---|---|
| Имитации сервисов | `backend/app/mcp_server/hiring.py`, `models.py` (`SkillSuggestion`) | Codex (#68) |
| База | `supabase/migrations/…skill_suggestions…` | Codex |
| HTTP | `backend/app/onboarding_api.py`: `/plan/items/{id}/known`, `/skills/suggestions`, `/skills/suggestions/{id}/decide` | Claude (#73) |
| Интерфейс | `frontend/src/components/PlanPanel.tsx` («Это я уже знаю»), `MentorTools.tsx` (`SkillSuggestions`) | Claude (#69) |

## 3. Данные и контракты
```
POST /plan/items/{id}/known {known: true|false}        → PlanItem (known_by_intern)
GET  /skills/suggestions?intern_id=…                    → {suggestions: [{id, intern_name, topic_title, from_level, to_level, basis, status}]}
POST /skills/suggestions/{id}/decide {accept: true|false} → SkillSuggestion
```

## 4. Проверка
Сервисные тесты (память и PostgreSQL), HTTP-тесты прав, тесты интерфейса. Вживую — шаги 4–7 маршрута README.

## 5. Риски и запасной вариант
Риск «бот оценивает человека» закрыт правилом: сервис не меняет уровень без решения наставника; отклонённые
предложения стажёру не видны.

## 6. Что заменяется при внедрении в Авито
Карта навыков — из системы найма/развития Авито; предложения — запись в её очередь согласований. Интерфейс и агент не
меняются.
