#!/usr/bin/env bash
# 【服务器 SSH / deploy】备份 ERP MySQL。密码来自容器环境变量，不出现在宿主机命令行。
set -Eeuo pipefail

ROOT="${NEORVION_ROOT:-/opt/neorvion}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/src/deploy/compose/docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-$ROOT/env/.env.production}"
OUT_DIR="${BACKUP_DIR:-$ROOT/backups/mysql}"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-14}"

mkdir -p "$OUT_DIR"
stamp="$(date +%Y%m%d-%H%M%S)"
outfile="$OUT_DIR/neorvion-${stamp}.sql.gz"

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

echo "backing up mysql to $outfile"
"${compose[@]}" exec -T mysql \
  sh -c 'mysqldump -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
  | gzip -c > "$outfile"

test -s "$outfile"
echo "backup size $(du -h "$outfile" | awk '{print $1}')"

# 只清理备份目录内超过保留天数的 .sql.gz，不碰其他路径。
find "$OUT_DIR" -maxdepth 1 -type f -name 'neorvion-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
echo "retention: deleted backups older than ${KEEP_DAYS} days in $OUT_DIR"
echo "$outfile"
