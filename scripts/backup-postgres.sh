#!/usr/bin/env bash
# 【服务器 SSH / deploy】备份 Knowledge 与 Copilot 共用实例中的两个独立数据库。
# ERP 不依赖 PostgreSQL；Knowledge/Copilot 的迁移和清理前必须保留可验证备份。
set -Eeuo pipefail

ROOT="${NEORVION_ROOT:-/opt/neorvion}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/src/deploy/compose/docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-$ROOT/env/.env.production}"
OUT_DIR="${BACKUP_DIR:-$ROOT/backups/postgres}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

mkdir -p "$OUT_DIR"
stamp="$(date +%Y%m%d-%H%M%S)"
compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

for database_var in POSTGRES_DB COPILOT_POSTGRES_DB; do
  database="$("${compose[@]}" exec -T postgres sh -c "printf '%s' \"\$$database_var\"")"
  if [[ -z "$database" ]]; then
    echo "$database_var is empty" >&2
    exit 1
  fi
  outfile="$OUT_DIR/${database}-${stamp}.sql.gz"
  echo "backing up $database to $outfile"
  "${compose[@]}" exec -T postgres \
    sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -U "$POSTGRES_USER" -d "$1"' sh "$database" \
    | gzip -c > "$outfile"
  test -s "$outfile"
  echo "$outfile"
done

find "$OUT_DIR" -maxdepth 1 -type f -name 'neorvion_*-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
