# Настройка для тиммейта (Codex)

## 1. Установить
- [Git](https://git-scm.com), [Node.js LTS](https://nodejs.org), [uv](https://docs.astral.sh/uv/), [VS Code](https://code.visualstudio.com)
- В VS Code: расширение **Codex** (OpenAI), войти своим аккаунтом ChatGPT.

## 2. Получить проект
Принять приглашение в репозиторий (придёт на почту GitHub), затем:
```bash
git clone https://github.com/<владелец>/ai-buddy.git
cd ai-buddy
```
Запуск — см. README. Файл `backend/.env` с ключами передаём лично, **не через репозиторий**.

## 3. Автоматическое ревью PR от Codex (рекомендуется)
[chatgpt.com/codex](https://chatgpt.com/codex) → Settings → Code review → подключить GitHub и включить ревью для репозитория `ai-buddy`.
Тогда Codex сам оставляет ревью к каждому PR (в том числе к PR от Claude).

## 4. Первое сообщение Codex (скопировать целиком)
```
Ты — Codex в командном проекте AI-buddy (хакатон Авито). Сначала прочитай AGENTS.md, .ai/STATUS.md,
.ai/claude-log.md, .ai/codex-log.md, .ai/HANDOFF.md, docs/SPEC.md и docs/API.md.
Твоя зона: backend/app/rag/ (RAG и поиск по документам), backend/app/mcp_server/ (MCP-сервер с моками
корпоративных сервисов), backend/app/db/ и схема БД Supabase. В чужие папки не лезь — пиши в HANDOFF.md.
Каждая задача — отдельная ветка codex/<задача> от свежего main. В main не пушь. После задачи обнови
.ai/codex-log.md и .ai/STATUS.md и открой Pull Request по шаблону. Секреты только в .env.
Скажи, что понял, и предложи, с какой задачи из STATUS.md начать.
```
