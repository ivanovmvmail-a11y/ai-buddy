# 105 — Персональный план: план реализации

## 1. Подход
У пункта плана появился тип: `common` (каркас и пункты команды, одинаковые у всех) или `personal` (из каталога по
теме, где у стажёра `новичок`). Персональные пункты строятся детерминированно из каталога в seed — без ИИ, поэтому
результат одинаков и без ключа. Пересборка вызывается при смене уровня (спека 202) и снимает только незакрытые
персональные пункты темы. Наставник правит персональные пункты через отдельные HTTP-методы; сервис сам проверяет
права (свой стажёр, только персональный, только незакрытый).

## 2. Что меняется
| Часть | Файлы / модули | Чья зона |
|---|---|---|
| Имитации сервисов | `backend/app/mcp_server/checklist.py` (`_rebuild_personal`, `list_catalog`, `add_personal_item`, `remove_personal_item`), `models.py` (`PlanItem.kind/reason/skill_level`, `CatalogItem`) | Codex (#67, #71) |
| Seed | `backend/app/mcp_server/seed/onboarding.json` (`personal_catalog`, Кирилл и Лиза) | Codex |
| База | `supabase/migrations/…personal…` | Codex |
| HTTP | `backend/app/onboarding_api.py`: `/plan/catalog`, `/plan/items`, `/plan/items/{id}`, `/plan/compare` | Claude (#77) |
| Агент | `backend/app/agent/onboarding_tools.py` (`plan_context`) | Claude |
| Интерфейс | `frontend/src/components/PlanPanel.tsx` (метки, «Убрать из плана», каталог), `MentorTools.tsx` (`ComparePlans`) | Claude |
| Контракт | `docs/API.md` | Claude |

## 3. Данные и контракты
```
GET  /plan?intern_id=intern-anya          → items[]: {id, title, kind: "common"|"personal", reason, topic, skill_level, …}
GET  /plan/catalog?intern_id=intern-anya  → {items: [{key, topic, topic_title, title}]}   # только наставник своего стажёра
POST /plan/items {intern_id, catalog_key} → 201 PlanItem
DELETE /plan/items/{id}                   → 204 · общий 403 · закрытый 409 · чужой 404
GET  /plan/compare?intern_ids=a,b         → {interns, common[{key,title,stage,topic,by_intern}], personal{intern_id: PlanItem[]}}
```

## 4. Проверка
Автотесты сервиса (память и PostgreSQL), HTTP-тесты прав, тесты интерфейса на метки и сравнение (таблица в
`spec.md`). Вживую — шаги 1 и 5 маршрута README.

## 5. Риски и запасной вариант
Правка наставником — «режем первой» (SPEC §13): если бы не успели, наставник влиял бы на план только через уровень.
Успели (#77).

## 6. Что заменяется при внедрении в Авито
Каталог — из базы знаний команды; план — из настоящего сервиса чек-листа через MCP. Агент и интерфейс не меняются:
они работают с полями `kind`, `reason`, `skill_level`.
