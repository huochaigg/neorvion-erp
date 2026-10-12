#!/usr/bin/env bash
# GitHub Actions 或服务器手动发布。不打印 Secret，不覆盖 .env.production。
set -Eeuo pipefail

ROOT="${NEORVION_ROOT:-/opt/neorvion}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/src/deploy/compose/docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-$ROOT/env/.env.production}"
export NEORVION_ENV_FILE="$ENV_FILE"
LOCK_FILE="${LOCK_FILE:-$ROOT/deploy.lock}"
RELEASES="${RELEASES_DIR:-$ROOT/releases}"
CURRENT="${CURRENT_DIR:-$ROOT/current}"
FRONTEND_STAGING="${FRONTEND_STAGING:-}"
NEW_SHA="${DEPLOY_SHA:?DEPLOY_SHA is required}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "missing $ENV_FILE" >&2
  exit 1
fi

# 让 Compose 插值与 env 文件一致，避免宿主机残留 MYSQL_DATABASE 等变量覆盖。
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "another deploy holds $LOCK_FILE" >&2
  exit 1
fi

echo "deploy start sha=$NEW_SHA"
old_image="$("${compose[@]}" images -q erp-api || true)"
echo "previous erp-api image id=${old_image:-none}"
printf '%s\n' "$NEW_SHA" >"$ROOT/previous_sha.txt.bak" || true
if [[ -f "$ROOT/current_sha.txt" ]]; then
  cp "$ROOT/current_sha.txt" "$ROOT/previous_sha.txt"
fi

echo "mysql backup"
"$ROOT/src/scripts/backup-mysql.sh"

echo "pull image"
"${compose[@]}" pull erp-api worker

echo "alembic upgrade head"
if ! "${compose[@]}" run --rm --no-deps erp-api uv run --no-dev alembic upgrade head; then
  echo "migration failed; API/worker not updated" >&2
  exit 1
fi

echo "compose up"
"${compose[@]}" up -d mysql redis postgres erp-api worker

echo "wait health"
ok=0
for _ in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8011/api/v1/health | grep -q '"app"'; then
    ok=1
    break
  fi
  sleep 2
done
if [[ "$ok" != 1 ]]; then
  echo "health check failed" >&2
  "${compose[@]}" ps
  "${compose[@]}" logs --tail=80 erp-api
  exit 1
fi

if [[ -n "$FRONTEND_STAGING" ]]; then
  dest="$RELEASES/$NEW_SHA"
  mkdir -p "$dest"
  if [[ -d "$FRONTEND_STAGING/shell" && -d "$FRONTEND_STAGING/erp" ]]; then
    rm -rf "$dest/shell" "$dest/erp"
    cp -a "$FRONTEND_STAGING/shell" "$dest/shell"
    cp -a "$FRONTEND_STAGING/erp" "$dest/erp"
    mkdir -p "$CURRENT"
    ln -sfn "$dest/shell" "$CURRENT/shell"
    ln -sfn "$dest/erp" "$CURRENT/erp"
    echo "frontend switched to $dest"
  else
    echo "WARN: frontend staging missing shell/erp, skip static switch"
  fi
fi

printf '%s\n' "$NEW_SHA" >"$ROOT/current_sha.txt"

echo "prune dangling images only (not prune -a)"
docker image prune -f >/dev/null || true

echo "deploy ok sha=$NEW_SHA"
curl -fsS http://127.0.0.1:8011/api/v1/health || true
echo
