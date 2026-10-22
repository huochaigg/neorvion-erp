#!/usr/bin/env bash
set -Eeuo pipefail

# 仅在 PostgreSQL 数据卷第一次初始化时执行。已有环境请按 Copilot README 手工迁移。
copilot_user="${COPILOT_POSTGRES_USER:-neorvion_copilot}"
copilot_password="${COPILOT_POSTGRES_PASSWORD:?COPILOT_POSTGRES_PASSWORD is required}"
copilot_db="${COPILOT_POSTGRES_DB:-neorvion_copilot}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=copilot_user="$copilot_user" --set=copilot_password="$copilot_password" <<'SQL'
SELECT format(
  'CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION',
  :'copilot_user', :'copilot_password'
) WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'copilot_user') \gexec
SQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
  --set=copilot_user="$copilot_user" --set=copilot_db="$copilot_db" <<'SQL'
SELECT format(
  'CREATE DATABASE %I OWNER %I ENCODING %L TEMPLATE template0',
  :'copilot_db', :'copilot_user', 'UTF8'
) WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'copilot_db') \gexec
SQL
