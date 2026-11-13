"""Переписка и черновики в PostgreSQL (SPEC §9): переживают перезапуск, изолированы по пользователю,
подтверждение атомарно. Нужен --mcp-postgres (общая одноразовая база с миграциями)."""
import asyncio

import psycopg

from app import async_runner
from app.agent.history import ChatEntry
from app.db.actions import PostgresActionStore
from app.db.history import PostgresHistoryStore

run = async_runner.run


def fresh(dsn):
    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute("DELETE FROM public.chat_messages")
        connection.execute("DELETE FROM public.agent_actions")


def test_history_survives_restart_and_is_per_user(onboarding_dsn):
    fresh(onboarding_dsn)
    store = PostgresHistoryStore(onboarding_dsn)
    try:
        run(store.append(ChatEntry(user_id="intern-anya", role="user", content="что дальше?")))
        run(store.append(ChatEntry(user_id="intern-anya", role="assistant", content="Следующий шаг…",
                                   sources=[{"title": "Первые дни стажёра", "url": None}], answer_id="ans_1", scripted=True)))
        run(store.append(ChatEntry(user_id="intern-ivan", role="user", content="чужое")))
    finally:
        run(store.close())

    restarted = PostgresHistoryStore(onboarding_dsn)  # «перезапуск backend»: новый объект, та же база
    try:
        anya = run(restarted.list("intern-anya"))
        assert [e.content for e in anya] == ["что дальше?", "Следующий шаг…"]  # старые сверху
        assert anya[1].sources == [{"title": "Первые дни стажёра", "url": None}] and anya[1].scripted
        assert anya[1].answer_id == "ans_1"
        assert [e.content for e in run(restarted.list("intern-anya", limit=1))] == ["Следующий шаг…"]
        assert run(restarted.list("intern-anya", limit=0)) == []
        assert [e.content for e in run(restarted.list("intern-ivan"))] == ["чужое"]
        run(restarted.clear())
        assert run(restarted.list("intern-anya")) == []
    finally:
        run(restarted.close())


def test_actions_survive_restart_and_claim_is_atomic(onboarding_dsn):
    fresh(onboarding_dsn)
    store = PostgresActionStore(onboarding_dsn)
    try:
        draft = run(store.create(user_id="intern-anya", tool="create_access_request", title="Заявка на доступ: Jira",
                                 params={"resource_id": "jira", "level": "read"}))
        assert draft.status == "pending" and draft.params == {"resource_id": "jira", "level": "read"}
    finally:
        run(store.close())

    restarted = PostgresActionStore(onboarding_dsn)
    try:
        assert run(restarted.get(draft.id)).title == "Заявка на доступ: Jira"  # черновик пережил перезапуск
        assert run(restarted.list_for("intern-ivan")) == []
        assert run(restarted.claim(draft.id, "intern-ivan")) is None  # чужой не может подтвердить

        async def both():  # два одновременных «Подтвердить»
            return await asyncio.gather(restarted.claim(draft.id, "intern-anya"), restarted.claim(draft.id, "intern-anya"))
        claimed = [a for a in run(both()) if a is not None]
        assert len(claimed) == 1 and claimed[0].status == "running"

        action = claimed[0]
        action.status, action.result = "done", {"status": "created", "request": {"id": "REQ-1"}}
        run(restarted.save(action))
        [saved] = run(restarted.list_for("intern-anya"))
        assert saved.status == "done" and saved.result["request"]["id"] == "REQ-1" and saved.updated_at >= saved.created_at
        assert run(restarted.claim(draft.id, "intern-anya")) is None  # уже выполнен
        assert run(restarted.get("act_missing")) is None
        run(restarted.clear())
        assert run(restarted.list_for("intern-anya")) == []
    finally:
        run(restarted.close())


def test_missing_table_falls_back_to_memory(onboarding_dsn, monkeypatch, caplog):
    """База без новой миграции (облако до применения SQL): чат работает в памяти и предупреждает один раз."""
    monkeypatch.setattr(PostgresHistoryStore, "table", "chat_messages_not_migrated")
    monkeypatch.setattr(PostgresActionStore, "table", "agent_actions_not_migrated")
    history, actions = PostgresHistoryStore(onboarding_dsn), PostgresActionStore(onboarding_dsn)
    try:
        run(history.append(ChatEntry(user_id="intern-anya", role="user", content="в памяти")))
        assert [e.content for e in run(history.list("intern-anya"))] == ["в памяти"]
        draft = run(actions.create(user_id="intern-anya", tool="t", title="T", params={}))
        assert run(actions.claim(draft.id, "intern-anya")).status == "running"
        assert run(actions.get(draft.id)) is not None and len(run(actions.list_for("intern-anya"))) == 1
        run(actions.save(run(actions.get(draft.id))))
        run(history.clear()), run(actions.clear())
        assert run(history.list("intern-anya")) == [] and run(actions.list_for("intern-anya")) == []
        assert sum("примените миграцию" in r.getMessage() for r in caplog.records) == 2
    finally:
        run(history.close()), run(actions.close())


def test_adapters_follow_database_url(monkeypatch):
    from app.config import settings
    from app.db.actions import postgres_action_store
    from app.db.history import postgres_history_store

    monkeypatch.setattr(settings, "database_url", "")
    assert postgres_history_store() is None and postgres_action_store() is None
    monkeypatch.setattr(settings, "database_url", "postgresql://u:p@127.0.0.1:1/db")
    assert isinstance(postgres_history_store(), PostgresHistoryStore)
    assert isinstance(postgres_action_store(), PostgresActionStore)


def test_app_picks_postgres_stores_on_real_import(tmp_path):
    """Найдено в Docker 13.11: циклический импорт молча оставлял переписку в памяти. Проверяем, как в gunicorn:
    чистый процесс, DATABASE_URL задан, импортируется само приложение."""
    import os
    import subprocess
    import sys
    code = ("import app.main; from app.agent import history, service; "
            "print(type(history.history).__name__, type(service.agent.store).__name__)")
    env = {**os.environ, "DATABASE_URL": "postgresql://u:p@127.0.0.1:1/db", "LLM_PROVIDER": "echo", "PYTHONUTF8": "1"}
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=60,
                         cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    assert out.stdout.split() == ["PostgresHistoryStore", "PostgresActionStore"], out.stderr[-2000:]
