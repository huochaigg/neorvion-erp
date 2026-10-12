#!/usr/bin/env bash
# 【危险操作：应用回滚】只换 Docker Image，不执行 alembic downgrade。
set -Eeuo pipefail

ROOT="${NEORVION_ROOT:-/opt/neorvion}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT/src/deploy/compose/docker-compose.production.yml}"
ENV_FILE="${ENV_FILE:-$ROOT/env/.env.production}"
TARGET_SHA="${ROLLBACK_SHA:?ROLLBACK_SHA is required, e.g. previous git commit}"
IMAGE_REPO="${IMAGE_REPO:?IMAGE_REPO is required, e.g. ghcr.io/owner/neorvion-erp/erp-api}"

export ERP_API_IMAGE="${IMAGE_REPO}:${TARGET_SHA}"
export GIT_SHA="$TARGET_SHA"
compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

echo "rolling back erp-api/worker to $ERP_API_IMAGE"
"${compose[@]}" pull erp-api worker
"${compose[@]}" up -d erp-api worker

curl -fsS http://127.0.0.1:8011/api/v1/health
echo
echo "app rollback done. database schema was NOT downgraded."
echo "if the old code cannot run on the current schema, restore MySQL backup instead."
