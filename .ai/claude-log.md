# Журнал Claude

Формат записи (новые сверху):
```
## ГГГГ-ММ-ДД — <задача> (ветка)
- Сделано:
- Дальше:
- Вопросы/блокеры:
- Что важно знать Codex:
```

## 2026-11-08 — каркас проекта (main, init)
- Сделано: правила (AGENTS.md, CLAUDE.md, .ai/), docs, backend FastAPI (/health, /chat, LLM-адаптер GigaChat + echo), frontend Next.js со страницей чата.
- Дальше: ждём ТЗ → /jmo-workflow:interview → docs/SPEC.md; деплой.
- Вопросы/блокеры: нет.
- Что важно знать Codex: заглушки для твоей зоны — `backend/app/rag/` и `backend/app/mcp_server/`. Контракт — `docs/API.md`.

## 2026-11-08 — сертификат GigaChat (claude/gigachat-cert)
- Сделано: корневой сертификат Минцифры в backend/certs/ (публичный, коммитится), GigaChat-адаптер подхватывает его автоматически — проверка SSL включена. Supabase-проект ai-buddy создан, pgvector включён. GigaChat проверен с локальной машины.
- Дальше: ждём ТЗ.
- Что важно знать Codex: Supabase URL/ключ и ключ GigaChat — в backend/.env, получи их у Миши лично. pgvector уже включён (схема extensions).
