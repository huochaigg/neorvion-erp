#!/usr/bin/env bash
# 【服务器 SSH / deploy】只读冒烟。不创建订单、不改库存。
set -Eeuo pipefail

BASE_LOCAL="${SMOKE_LOCAL_API:-http://127.0.0.1:8011}"
BASE_PUBLIC="${SMOKE_PUBLIC_BASE:-https://neorvion.com}"

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

echo "1) local FastAPI health"
health="$(curl -fsS "$BASE_LOCAL/api/v1/health")"
echo "$health"
echo "$health" | grep -q '"app":"ok"' || echo "$health" | grep -q '"app": "ok"' || fail "health app not ok"

echo "2) local RSA public key"
curl -fsS "$BASE_LOCAL/api/crypto/public-key" | grep -q public_key || fail "public-key missing"

echo "3) public homepage (if HTTPS already on)"
if curl -fsS -o /dev/null -w "%{http_code}" "$BASE_PUBLIC/" | grep -Eq '200|301|302'; then
  echo "public / reachable"
else
  echo "WARN: $BASE_PUBLIC/ not reachable yet (DNS/SSL may be unfinished)"
fi

echo "4) public /erp/"
if curl -fsS -o /dev/null -w "%{http_code}" "$BASE_PUBLIC/erp/" | grep -Eq '200|301|302'; then
  echo "public /erp/ reachable"
else
  echo "WARN: $BASE_PUBLIC/erp/ not reachable yet"
fi

echo "5) public API health via nginx (optional)"
if curl -fsS "$BASE_PUBLIC/api/v1/health" >/tmp/neorvion-smoke-health.json 2>/dev/null; then
  cat /tmp/neorvion-smoke-health.json
  echo
else
  echo "WARN: public /api/v1/health not reachable yet"
fi

echo "smoke finished (local API required, public checks may warn)"
