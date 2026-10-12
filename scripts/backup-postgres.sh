#!/usr/bin/env bash
# 【服务器 SSH / deploy】备份未来 Agent 用的 PostgreSQL。
# ERP 不依赖本库。没有 Agent 数据时，这不是上线必备备份。
set -Eeuo pipefail

ROOT="${NEORVION_ROOT:-/opt/neorvion}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/src/deploy/compose/docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-$ROOT/env/.env.production}"
OUT_DIR="${BACKUP_DIR:-$ROOT/backups/postgres}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

mkdir -p "$OUT_DIR"
stamp="$(date +%Y%m%d-%H%M%S)"
outfile="$OUT_DIR/neorvion-agent-${stamp}.sql.gz"

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

echo "backing up postgres to $outfile"
"${compose[@]}" exec -T postgres \
  sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
  | gzip -c > "$outfile"

test -s "$outfile"
find "$OUT_DIR" -maxdepth 1 -type f -name 'neorvion-agent-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
echo "$outfile"
