#!/bin/sh
set -eu
# Только локальная Docker-БД. Случайный пароль не печатается и не передаётся через argv.
export PGHOST=db PGUSER=buddy PGDATABASE=ai_buddy PGPASSWORD=buddy
umask 077
if [ ! -s /secrets/password ]; then
    psql -X -At -v ON_ERROR_STOP=1 -c "SELECT replace(gen_random_uuid()::text, '-', '')" > /secrets/password
fi
export GRAFANA_SQL_PASSWORD="$(cat /secrets/password)"
psql -X -v ON_ERROR_STOP=1 -f /provision/metrics.sql
psql -X -v ON_ERROR_STOP=1 <<'SQL'
\getenv reader_password GRAFANA_SQL_PASSWORD
ALTER ROLE ai_buddy_grafana LOGIN PASSWORD :'reader_password';
SQL
chown 472:472 /secrets/password
chmod 0400 /secrets/password
