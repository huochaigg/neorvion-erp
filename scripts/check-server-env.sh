#!/usr/bin/env bash
# 【服务器 SSH】只读检查，不修改任何配置。
set -Eeuo pipefail

echo "=== OS ==="
if [[ -f /etc/os-release ]]; then
  . /etc/os-release
  echo "NAME=${NAME:-}"
  echo "VERSION=${VERSION:-}"
  echo "ID=${ID:-}"
else
  echo "os-release missing"
fi
uname -r

echo
echo "=== CPU / Memory / Swap / Disk ==="
nproc
free -h
df -h /

echo
echo "=== Docker ==="
if command -v docker >/dev/null 2>&1; then
  docker --version
  docker compose version || echo "docker compose plugin missing"
  systemctl is-active docker || true
else
  echo "docker not installed"
fi

echo
echo "=== Listening ports (ss) ==="
if command -v ss >/dev/null 2>&1; then
  ss -lntp || ss -lnt
else
  echo "ss not available"
fi

echo
echo "=== BT / Nginx paths (existence only) ==="
[[ -d /www/server/nginx ]] && echo "/www/server/nginx exists" || echo "/www/server/nginx missing"
[[ -d /www/server/mysql ]] && echo "/www/server/mysql exists" || echo "/www/server/mysql missing"
[[ -d /www/server/redis ]] && echo "/www/server/redis exists" || echo "/www/server/redis missing"
command -v nginx >/dev/null 2>&1 && nginx -v || true
[[ -x /www/server/nginx/sbin/nginx ]] && /www/server/nginx/sbin/nginx -v || true

echo
echo "=== Python / Git / Node (host, ERP 生产不依赖宿主机 Python/Node) ==="
python3 --version || true
git --version || true
command -v node >/dev/null 2>&1 && node --version || echo "node not installed (expected on production)"

echo
echo "done"
