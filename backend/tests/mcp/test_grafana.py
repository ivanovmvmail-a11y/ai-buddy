"""Настоящие SQL-запросы панели и ограничение прав datasource (временный PostgreSQL)."""
import json
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict
from psycopg.types.json import Jsonb
import pytest

from app.agent.analytics import closed_without_human
from .conftest import MIGRATION

ROOT = Path(__file__).resolve().parents[3]
METRICS = ROOT / 'supabase/migrations/20261111100000_grafana_metrics.sql'
DASHBOARD = ROOT / 'ops/grafana/dashboards/onboarding.json'


@pytest.fixture
def metrics_database(onboarding_dsn):
    params = conninfo_to_dict(onboarding_dsn)
    name = 'grafana_test_' + uuid4().hex
    with psycopg.connect(**{**params, 'dbname': 'postgres'}, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        try:
            yield {**params, 'dbname': name}
        finally:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_dashboard_has_expected_panels_without_identity_columns():
    dashboard = json.loads(DASHBOARD.read_text(encoding='utf-8'))
    assert dashboard['uid'] == 'ai-buddy-demo' and dashboard['refresh'] == '5s'
    assert len(dashboard['panels']) == 10
    assert len({panel['id'] for panel in dashboard['panels']}) == 10
    for panel in dashboard['panels']:
        query = panel['targets'][0]['rawSql']
        assert 'public.grafana_' in query
        assert not any(name in query for name in ('user_id', 'intern_id', 'payload', 'public.events'))


@pytest.mark.parametrize('has_onboarding', [False, True])
def test_metrics_migration_handles_empty_legacy_database_and_repeated_provisioning(metrics_database, has_onboarding):
    with psycopg.connect(**metrics_database, autocommit=True) as owner:
        if has_onboarding:
            owner.execute(MIGRATION.read_text(encoding='utf-8'))
        owner.execute(METRICS.read_text(encoding='utf-8'))
        owner.execute(METRICS.read_text(encoding='utf-8'))
        assert owner.execute('SELECT count(*) FROM grafana_answers').fetchone() == (0,)
        assert owner.execute('SELECT count(*) FROM grafana_feedback').fetchone() == (0,)
        if not has_onboarding:
            owner.execute(MIGRATION.read_text(encoding='utf-8'))
            owner.execute(METRICS.read_text(encoding='utf-8'))
            owner.execute("INSERT INTO events (ts,user_id,role,team,type,payload) VALUES (now(),'system','system','system','question_answered',%s)",
                          (Jsonb({'intern_id': 'intern-anya', 'topic': 'git'}),))
            assert owner.execute('SELECT count(*) FROM grafana_answers').fetchone() == (1,)


def test_panel_sql_matches_metrics_and_reader_cannot_read_private_tables_or_write(metrics_database):
    params = metrics_database
    answers = [
        {'intern_id': 'intern-anya', 'topic': 'git', 'with_source': True, 'latency_ms': 100},
        {'intern_id': 'intern-ivan', 'topic': 'plan', 'tools': ['get_plan'], 'latency_ms': 200},
        {'intern_id': 'intern-anya', 'topic': 'hr', 'with_source': True},
        {'intern_id': 'intern-anya', 'topic': 'environment', 'not_in_base': True},
        {'intern_id': 'intern-ivan', 'topic': 'git', 'with_source': True, 'refused': True},
    ]
    with psycopg.connect(**params, autocommit=True) as owner:
        owner.execute(MIGRATION.read_text(encoding='utf-8'))
        owner.execute(METRICS.read_text(encoding='utf-8'))
        owner.execute("ALTER ROLE ai_buddy_grafana LOGIN PASSWORD 'grafana-test-only'")
        for payload in answers + [{'user_id': 'mentor-petr', 'topic': 'git', 'with_source': True}]:
            owner.execute("INSERT INTO events (ts,user_id,role,team,type,payload) VALUES (now(),'system','system','system','question_answered',%s)",
                          (Jsonb({**payload, 'question': 'не должен попадать в представление'}),))
        for useful in (True, False):
            owner.execute("INSERT INTO events (ts,user_id,role,team,type,payload) VALUES (now(),'system','system','system','answer_feedback',%s)",
                          (Jsonb({'intern_id': 'intern-anya', 'useful': useful}),))
    with psycopg.connect(**{**params, 'user': 'ai_buddy_grafana', 'password': 'grafana-test-only'}, autocommit=True) as reader:
        assert reader.execute('SHOW default_transaction_read_only').fetchone() == ('on',)
        assert reader.execute('SELECT count(*),sum(closed_without_human::int) FROM grafana_answers').fetchone() == (5, sum(map(closed_without_human, answers)))
        for panel in json.loads(DASHBOARD.read_text(encoding='utf-8'))['panels']:
            query = panel['targets'][0]['rawSql'].replace("$__timeGroupAlias(ts,'1d')", "date_trunc('day',ts) AS time").replace('$__timeFilter(ts)', 'true')
            cursor = reader.execute(query)
            cursor.fetchall()  # Каждый настоящий запрос панели исполняется ограниченным пользователем.
            assert not {'user_id', 'intern_id', 'payload'} & {column.name for column in cursor.description}
        for table in ('events', 'plan_items', 'skill_profiles', 'access_requests'):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                reader.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table)))
        # Даже отключение default read-only не даёт прав изменять таблицы/представления.
        reader.execute('SET default_transaction_read_only=off')
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader.execute("DELETE FROM events")
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            reader.execute("DELETE FROM grafana_answers")
