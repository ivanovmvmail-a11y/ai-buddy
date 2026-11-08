# API — контракт frontend ↔ backend

Базовый URL: `http://localhost:8000` локально, на проде — `NEXT_PUBLIC_API_URL`.
Меняется только PR с пометкой `[API]`.

## GET /health
Ответ `200`:
```json
{ "status": "ok", "llm_provider": "gigachat" }
```

## POST /chat
Запрос:
```json
{
  "messages": [
    { "role": "user", "content": "Как получить доступ к GitLab?" }
  ]
}
```
`role`: `user` | `assistant`. История передаётся целиком (бэкенд stateless).

Ответ `200`:
```json
{
  "reply": "Текст ответа помощника",
  "sources": [ { "title": "Онбординг-гайд", "url": null } ]
}
```
`sources` — документы, найденные RAG (пока всегда пустой список).

Ошибка LLM → `502` `{ "detail": "..." }`.
