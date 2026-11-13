"""S2: реальные инструкции для четырёх шагов, права команд и ответы без модели."""
from app import async_runner
from app.agent import explain
from app.agent.users import DEMO_USERS
from app.mcp_server import checklist
from app.rag.ingest import DEMO_DOCS, read_document
import pytest

run = async_runner.run


@pytest.mark.parametrize("user_id,topic,expected_source", [
    ("intern-anya", "team-space", "13-team-space-access.md"),
    ("intern-ivan", "team-space", "13-team-space-access.md"),
    ("intern-anya", "sandbox", "17-platform-sandbox-setup.md"),
    ("intern-ivan", "sandbox", "20-delivery-sandbox-setup.md"),
])
def test_plan_source_is_an_accessible_howto_and_explanation_cites_it(
    store, user_id, topic, expected_source
):
    user = DEMO_USERS[user_id]
    plan = run(checklist.get_plan(user, user_id))
    item = next(item for item in plan.items if item.id.endswith(f"w1.{topic}"))
    assert item.doc_source_id == f"demo:{expected_source}"
    document = read_document(DEMO_DOCS / expected_source, item.doc_source_id)
    assert document.team in (None, user.team)
    for kind in ("explain", "steps"):
        result = run(explain.explain_item(user, user_id, item.id, kind))
        assert result["with_source"] and result["source"]["title"] == document.title
        assert result["source"]["url"].endswith(expected_source)
        if topic == "team-space":
            assert "заявкой на доступ" in result["text"]
            if kind == "steps":
                assert "согласует твой наставник" in result["text"]
        else:
            assert "Как поднять песочницу" in result["text"]


@pytest.mark.parametrize("custom_source", [False, True])
def test_existing_plan_source_patch_preserves_progress_and_operator_links(onboarding_dsn, custom_source):
    import psycopg
    from psycopg.rows import dict_row
    from app.mcp_server.postgres import PostgresStore
    from app.mcp_server.seed import load_seed
    from .conftest import MIGRATION

    seed = load_seed()
    links = {
        "anya.w1.team-space": ("demo:05-platform-sandbox.md", "demo:13-team-space-access.md"),
        "ivan.w1.team-space": ("demo:08-delivery-sandbox.md", "demo:13-team-space-access.md"),
        "anya.w1.sandbox": ("demo:05-platform-sandbox.md", "demo:17-platform-sandbox-setup.md"),
        "ivan.w1.sandbox": ("demo:08-delivery-sandbox.md", "demo:20-delivery-sandbox-setup.md"),
    }
    for item_id, (old, _) in links.items():
        seed.items[item_id].doc_source_id = old
    seed.items["anya.w1.team-space"].status = "waiting"
    seed.items["anya.w1.team-space"].waiting_for = "mentor-petr"
    if custom_source:
        seed.items["anya.w1.sandbox"].doc_source_id = "demo:operator-custom.md"
    store = PostgresStore(onboarding_dsn)
    try:
        run(store.initialize(seed, reset=True))
        with psycopg.connect(onboarding_dsn, autocommit=True, row_factory=dict_row) as connection:
            before = connection.execute("SELECT * FROM public.plan_items ORDER BY id").fetchall()
            patch = MIGRATION.with_name("20261111154000_howto_plan_sources.sql").read_text()
            connection.execute(patch)
            after = connection.execute("SELECT * FROM public.plan_items ORDER BY id").fetchall()
            for old_row, new_row in zip(before, after, strict=True):
                expected = dict(old_row)
                pair = links.get(old_row["id"])
                if pair and old_row["doc_source_id"] == pair[0]:
                    expected["doc_source_id"] = pair[1]
                assert new_row == expected
            connection.execute(patch)
            assert connection.execute("SELECT * FROM public.plan_items ORDER BY id").fetchall() == after
    finally:
        run(store.close())
