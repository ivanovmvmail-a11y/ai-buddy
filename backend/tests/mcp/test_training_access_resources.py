"""Общие учебные ресурсы: автоматический read и безопасное обновление каталога."""
import psycopg
import pytest

from app import async_runner
from app.agent.users import DEMO_USERS
from app.mcp_server import access, checklist
from app.mcp_server.models import OnboardingData
from app.mcp_server.postgres import PostgresStore
from app.mcp_server.seed import load_seed
from .conftest import MIGRATION

run = async_runner.run
CATALOG_MIGRATION = MIGRATION.with_name('20261112170044_access_training_resources.sql')
TITLES = {'redash': 'Учебный Redash', 'grafana': 'Учебная Grafana'}


@pytest.mark.parametrize('user_id', ['intern-anya', 'intern-kirill', 'intern-ivan', 'intern-liza'])
@pytest.mark.parametrize('resource_id', TITLES)
def test_training_resource_read_is_immediate_and_keeps_base_plan(store, snapshot, user_id, resource_id):
    actor = DEMO_USERS[user_id]
    before = snapshot()
    resource = next(r for r in run(access.list_resources(actor)) if r.id == resource_id)
    assert resource.title == TITLES[resource_id]
    assert resource.team is None and resource.kind == 'base' and resource.approver == 'auto'
    assert resource.fields == before.resources['jira'].fields
    assert next(field for field in resource.fields if field['name'] == 'level')['default'] == 'read'
    request = run(access.create_request(actor, resource_id, 'read', 'Изучить учебные данные'))
    assert request.status == 'granted' and request.level == 'read'
    assert request.approver_id is None and request.plan_item_id is None
    assert request.id in {r.id for r in run(access.list_requests(actor))}
    after = snapshot()
    assert after.items == before.items  # Запрос Redash/Grafana не закрывает пункт про Jira.
    base_item = next(item for item in after.items.values()
                     if item.intern_id == user_id and item.id.endswith('.w1.access-base'))
    assert base_item.resource_id == 'jira'
    created, decided = after.events[len(before.events):]
    assert created.type == 'access_request_created' and created.user_id == user_id
    assert decided.type == 'access_request_decided' and decided.user_id == 'system'
    assert decided.payload['approver'] == 'auto'


@pytest.mark.parametrize('populated', [False, True], ids=['empty-bootstrap', 'existing-progress'])
def test_catalog_migration_is_idempotent_without_resetting_progress(store, edit, snapshot, populated):
    if not isinstance(store, PostgresStore):
        pytest.skip('Requires --mcp-postgres')
    if populated:
        run(checklist.set_item_status(DEMO_USERS['intern-anya'], 'anya.w1.notes', 'done'))
        edit(lambda data: [data.resources.pop(key) for key in TITLES])
    else:
        run(store.initialize(OnboardingData(), reset=True))
    before = snapshot()
    with psycopg.connect(store.database_url, autocommit=True) as connection:
        for _ in range(2):
            connection.execute(CATALOG_MIGRATION.read_text(encoding='utf-8'))
    after = snapshot()
    if populated:
        seed = load_seed()
        for key in TITLES:
            assert after.resources.pop(key) == seed.resources[key]
    assert after == before  # Включая текущий день, планы, заявки, напоминания и events.
    run(store.initialize(load_seed()))
    initialized = snapshot()
    assert set(TITLES) <= initialized.resources.keys()
    assert initialized.interns and initialized.items
    if populated:
        assert initialized.items['anya.w1.notes'].status == 'done'
