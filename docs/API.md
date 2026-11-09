# API — контракт frontend ↔ backend

Базовый URL: `http://localhost:8000` локально, на проде — `NEXT_PUBLIC_API_URL`.
Меняется только PR с пометкой `[API]`.

## Пользователь (имитация авторизации)
Все запросы, кроме `/health`, выполняются от имени пользователя из заголовка `X-User-Id`.
- Нет заголовка → демо-стажёр `intern-anya`.
- Неизвестный id → `401 {"detail": "Неизвестный пользователь"}`.

Демо-пользователи (синтетические): `intern-anya`, `intern-ivan` (стажёры), `mentor-petr`, `mentor-maria` (наставники),
`lead-olga`, `lead-sergey` (руководители), `hrbp-elena` (HR BP), `curator-dmitry` (куратор).
В Авито заголовок заменяется корпоративным SSO; список — в `backend/app/agent/users.py`.

## GET /health
Ответ `200`:
```json
{ "status": "ok", "llm_provider": "gigachat" }
```

## GET /me
Текущий пользователь. Ответ `200`:
```json
{ "id": "intern-anya", "name": "Аня Смирнова", "role": "intern", "team": "Платформа объявлений",
  "mentor_id": "mentor-petr", "lead_id": "lead-olga" }
```
`role`: `intern` | `mentor` | `lead` | `hrbp` | `curator`.

## POST /chat
Запрос:
```json
{
  "messages": [
    { "role": "user", "content": "Напомни 20 ноября запросить доступ к GitLab" }
  ]
}
```
`role`: `user` | `assistant` (`system` принимается, но игнорируется — системный промпт задаёт сервер).
История передаётся целиком.

Ответ `200`:
```json
{
  "reply": "Подготовил черновик напоминания. Проверь и нажми «Подтвердить».",
  "sources": [ { "title": "Онбординг-гайд", "url": null } ],
  "actions": [ <Action> ]
}
```
- `sources` — документы, найденные RAG.
- `actions` — **черновики**, которые агент подготовил в этом ответе (`status: "pending"`). Фронт показывает
  карточку с кнопками «Подтвердить» / «Отменить». Без подтверждения ничего не выполняется.

Ошибки: `422` — неверное тело запроса; `502 {"detail": "Ошибка LLM: ..."}` — сбой модели.

## Action
```json
{
  "id": "act_dd9dd115ae1d",
  "user_id": "intern-anya",
  "tool": "create_reminder",
  "title": "Напоминание на 20.11.2026: запросить доступ к GitLab",
  "params": { "text": "запросить доступ к GitLab", "remind_on": "2026-11-20" },
  "status": "pending",
  "result": null,
  "error": null,
  "created_at": "2026-11-09T22:48:29.437281Z",
  "updated_at": "2026-11-09T22:48:29.437281Z"
}
```
`status`: `pending` (черновик) → `done` (выполнено, `result` — ответ сервиса) | `failed` (`error` — текст ошибки) | `cancelled`.

## GET /actions
Действия текущего пользователя, новые сверху: `200 {"actions": [<Action>, ...]}`. Чужие не видны.

## POST /actions/{id}/confirm
Выполнить черновик. Права проверяются повторно.
- `200 <Action>` со статусом `done` или `failed`;
- `404` — нет такого действия **или оно чужое** (факт существования чужих действий не раскрывается);
- `409` — действие уже не `pending`;
- `403` — права на действие отозваны.

## POST /actions/{id}/cancel
Отменить черновик: `200 <Action>` со статусом `cancelled`; `404` / `409` — как у confirm.
