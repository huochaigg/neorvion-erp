# 腾讯云 OpenCloudOS 9.2 第一次生产部署

只看这一份，可以完成 **第一次手工上线**。日常发布见文末「B. 以后自动发布」，细节见 `docs/github-cicd.md`。运维排障见 `docs/server-operations.md`。

本文 **不是**「已经在腾讯云部署成功」的记录。你必须自己 SSH、自己执行。

系统是 **OpenCloudOS 9.2**，安装用 `dnf`，不要用 `apt`。

身份中心是 **IAM :8010**，不是 ERP。ERP 业务 API 仍是 **8011**，Knowledge API 是 **8012**。公网只经 Nginx：登录/刷新/租户/角色/会话/JWKS 反代 IAM；Knowledge 专用前缀反代 8012；其余 `/api/` 反代 ERP。**禁止**把 Knowledge API 一并打到 8011。

ERP 数据库是 **MySQL `neorvion_erp`**。IAM 数据库是 **MySQL `neorvion_iam`**。PostgreSQL + pgvector 给 Knowledge。JWT / RSA 私钥只挂到 IAM 容器，不要打进镜像或提交 Git。

生产 **不要**在服务器装 Node.js。前端在本地或 GitHub Actions 构建。宿主机 Python **不用于**跑业务进程。

---

## A. 第一次部署（全部手动）

### 第一阶段：确认腾讯云服务器

【腾讯云控制台】云服务器 → 实例

记下：公网 IP、地域、是否中国大陆。后面用 `YOUR_SERVER_IP` 代替。

【服务器 SSH / root】

```bash
cat /etc/os-release
```

预期包含：`NAME="OpenCloudOS"`、`VERSION="9.2"`、`ID="opencloudos"`。

```bash
ss -lntp
```

预期能看到 `0.0.0.0:8888`（宝塔）。当前 **不应** 看到 80/443/3306/5432/6379/8011。

---

### 第二阶段：腾讯云安全组

【腾讯云控制台】实例 → 安全组 → 入站规则

应开放：

| 端口 | 来源 | 用途 |
| --- | --- | --- |
| 22 | **只你的家庭/公司公网 IP** | SSH |
| 80 | `0.0.0.0/0` | HTTP / 申请证书 |
| 443 | `0.0.0.0/0` | HTTPS |
| 8888 | **只你的公网 IP** | 宝塔（当前已在 0.0.0.0:8888 监听，真正能否从公网进仍看安全组） |

**不要**开放：3306、5432、6379、8011、8001。

如何确认自己的公网 IP：本地浏览器打开「IP 查询」，把结果填成 `x.x.x.x/32`。

---

### 第三阶段：SSH 与基础安全

继续用 root 做完初始化可以。之后 GitHub **禁止**用 root 私钥。

【本地 Windows PowerShell】用你现有的登录方式 SSH 进去即可。不要把个人无关私钥复用成分发密钥。

---

### 第四阶段：OpenCloudOS 初始化

【服务器 SSH / root】

步骤 4.1 更新（时间可能较长）：

```bash
dnf -y update
```

预期：完成或 `Nothing to do`。

步骤 4.2 常用工具：

```bash
dnf -y install curl wget git tar gzip unzip vim firewalld
```

步骤 4.3 2C2G 建议加 2G Swap（内存紧张时用，不能替代升级）：

```bash
free -h
```

若 Swap 为 0：

```bash
fallocate -l 2G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
free -h
```

预期：`Swap` 一行总大小约 2Gi。

**【检查点：系统】** `cat /etc/os-release` 为 OpenCloudOS 9.2，`free -h` 能看到 Swap。再继续。

---

### 第五阶段：安装 Docker Engine

OpenCloudOS 9.2 兼容 EL9。Docker 官方仓库按 **centos/9** 使用。若 `$releasever` 是 `9.2` 导致 404，把仓库里的 `$releasever` 写成 `9`。

步骤 5.1 若已有 podman 等冲突包（没有也不报错）：

```bash
dnf -y remove podman buildah runc || true
```

步骤 5.2 仓库：

```bash
dnf -y install dnf-plugins-core
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sed -i 's/\$releasever/9/g' /etc/yum.repos.d/docker-ce.repo
dnf -y makecache
```

步骤 5.3 安装：

```bash
dnf -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

步骤 5.4 启动：

```bash
systemctl enable --now docker
```

**【检查点：Docker】**

```bash
docker --version
docker compose version
systemctl status docker --no-pager
```

预期：`Docker version 2x.x.x`，`Docker Compose version v2.x.x`，docker 为 `active (running)`。

不要 `chmod 777 /var/run/docker.sock`。

---

### 第六阶段：Compose Plugin

上一步已经安装 `docker-compose-plugin`。不要再装旧的 `docker-compose` 1.x。

```bash
docker compose version
```

---

### 第七阶段：宝塔安装 Nginx

【宝塔网页】登录面板（`http://YOUR_SERVER_IP:8888`，按你的安全入口）→ 软件商店 → 搜索 **Nginx** → 安装推荐稳定版。

**不要**再装宝塔 MySQL / Redis。ERP 用 Docker 数据库。两套 MySQL 会打架。

【服务器 SSH / root】

```bash
ls /www/server/nginx
ss -lntp | grep ':80' || true
```

预期：`/www/server/nginx` 存在。装完后可能已监听 80。

---

### 第八阶段：目录与 deploy 用户

步骤 8.1 创建用户【服务器 SSH / root】：

```bash
id deploy 2>/dev/null || useradd -m -s /bin/bash deploy
usermod -aG docker deploy
```

`docker` 组权限很高，等同接近 root。这是为了让 GitHub 用 `deploy` 跑 Compose，**仍然不要**把 root 私钥给 GitHub。

步骤 8.2 部署目录：

```bash
mkdir -p /opt/neorvion/{env,secrets/rsa/v1,scripts,backups/mysql,backups/postgres,logs,releases,current,staging,data/exports,src}
chown -R deploy:deploy /opt/neorvion
chmod 750 /opt/neorvion
chmod 700 /opt/neorvion/env /opt/neorvion/secrets
```

| 路径 | 作用 |
| --- | --- |
| `/opt/neorvion/src` | git clone，**不含**真实密码 |
| `/opt/neorvion/env` | `.env.production`，不进 Git |
| `/opt/neorvion/secrets/rsa` | RSA 私钥，不进 Git |
| `/opt/neorvion/backups` | 数据库备份 |
| `/opt/neorvion/current` | 当前前端静态目录的符号链接 |
| `/opt/neorvion/releases` | 按 SHA 保存的前端 |

数据库文件在 **Docker Named Volume**，不放 Git 仓库里。

步骤 8.3 Deploy SSH Key【本地 Windows PowerShell】（一套**专用**密钥，不要复用你日常 GitHub 钥匙）：

```powershell
ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\neorvion_deploy -C "neorvion-production-deploy" -N ""
```

会生成 `neorvion_deploy`（私钥，将来贴 GitHub Secret）和 `neorvion_deploy.pub`。

【服务器 SSH / root】：

```bash
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
# 把公钥内容追加到 authorized_keys 后：
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh
```

【本地 Windows PowerShell】测试：

```powershell
ssh -i $env:USERPROFILE\.ssh\neorvion_deploy deploy@YOUR_SERVER_IP
```

预期：不用密码进入，提示符是 `deploy@...`。

重新登录后验证 Docker：

```bash
docker ps
```

预期：能列出容器（可能为空表），**不要** Permission denied。若失败，确认已加入 docker 组并 **重新 SSH**。

---

### 第九–十阶段：生产环境变量与密钥

【服务器 SSH / deploy】clone（把地址换成你的仓库）：

```bash
git clone https://github.com/YOUR_GITHUB_OWNER/neorvion-erp.git /opt/neorvion/src
cd /opt/neorvion/src
```

复制模板：

```bash
cp /opt/neorvion/src/.env.production.example /opt/neorvion/env/.env.production
chmod 600 /opt/neorvion/env/.env.production
```

生成随机值【服务器 SSH / deploy】（把输出填进 `.env.production`，不要用 `password123`）：

```bash
openssl rand -hex 48
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 24
openssl rand -hex 24
```

五个结果分别建议给：`SECRET_KEY`、`MYSQL_ROOT_PASSWORD`、`MYSQL_PASSWORD`、`REDIS_PASSWORD`、`POSTGRES_PASSWORD`。

还要改：

- `ERP_API_IMAGE=neorvion-erp-api:local`（第一次本地构建）
- `CORS_ORIGINS=https://neorvion.com,https://www.neorvion.com`
- `APP_ENV=production`
- `REFRESH_COOKIE_SECURE=true`
- `MYSQL_USER=neorvion`（应用禁止用 root）

生成 RSA【服务器 SSH / deploy】（PKCS#8 私钥 + SPKI 公钥，与项目 `rsa_crypto.py` 一致。不要依赖宿主机 Python）：

```bash
mkdir -p /opt/neorvion/secrets/rsa/v1
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 \
  -out /opt/neorvion/secrets/rsa/v1/private.pem
openssl pkey -in /opt/neorvion/secrets/rsa/v1/private.pem -pubout \
  -out /opt/neorvion/secrets/rsa/v1/public.pem
chmod 600 /opt/neorvion/secrets/rsa/v1/private.pem
chmod 644 /opt/neorvion/secrets/rsa/v1/public.pem
ls -l /opt/neorvion/secrets/rsa/v1
```

预期：两个 `.pem` 文件，私钥权限 `600`。私钥 **禁止**提交 Git。

镜像构建完成之后，也可以用仓库脚本（二选一即可，不要覆盖已在用的生产私钥）：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f /opt/neorvion/src/deploy/compose/docker-compose.production.yml \
  run --rm --no-deps -v /opt/neorvion/secrets/rsa:/out \
  erp-api uv run --no-dev python scripts/generate_rsa_keys.py --key-id v1 --out-dir /out
```

---

### 第十一阶段：启动 MySQL / Redis / PostgreSQL

【服务器 SSH / deploy】每次新开 SSH 先载入 env（避免宿主机碰巧 export 的 `MYSQL_DATABASE` 覆盖 Compose）：

```bash
set -a
source /opt/neorvion/env/.env.production
set +a
export NEORVION_ENV_FILE=/opt/neorvion/env/.env.production
cd /opt/neorvion/src
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  up -d mysql redis postgres
```

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml ps
```

**【检查点：数据库】** 三个服务均为 running，mysql / redis / postgres 的 STATUS 含 `(healthy)`。若长时间 unhealthy：`docker compose ... logs mysql`。

查看 volume：

```bash
docker volume ls | grep neorvion
```

预期：`neorvion_mysql_data`、`neorvion_redis_data`、`neorvion_postgres_data`。

---

### 第十二阶段：验证数据库

MySQL【服务器 SSH / deploy】：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  exec mysql mysql -uneorvion -p"$MYSQL_PASSWORD" -e "SELECT DATABASE();"
```

把 `$MYSQL_PASSWORD` 换成你在 env 里的应用密码，或：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  exec mysql sh -c 'mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" -e "SHOW DATABASES;"'
```

预期能看到 `neorvion_erp`。字符集应为 utf8mb4。

Redis：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  exec redis sh -c 'redis-cli -a "$REDIS_PASSWORD" ping'
```

预期：`PONG`。

PostgreSQL + pgvector：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  exec postgres sh -c 'PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE EXTENSION IF NOT EXISTS vector; SELECT extname FROM pg_extension WHERE extname = '"'"'vector'"'"';"'
```

预期一行：`vector`。

---

### 第十三阶段：构建并启动 FastAPI / Worker

第一次还没有 GHCR 镜像，在服务器构建（只要 Docker，不要 Node）：

```bash
cd /opt/neorvion/src
export GIT_SHA="$(git rev-parse HEAD)"
export ERP_API_IMAGE=neorvion-erp-api:local
export NEORVION_ENV_FILE=/opt/neorvion/env/.env.production
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  -f deploy/compose/docker-compose.build.yml \
  build erp-api
```

预期：镜像构建成功。把 `.env.production` 里 `ERP_API_IMAGE` 写成 `neorvion-erp-api:local`。

启动 API 与 Worker（此时 **还不要**指望容器自己跑 Alembic）：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  up -d erp-api worker
```

`erp-api` 依赖 mysql/redis **healthy**，不依赖 postgres。Worker **不映射任何端口**。

---

### 第十四阶段：Alembic（独立步骤）

Migration **失败就不要继续当网站已上线**。不要让每个 API 容器启动时自动 upgrade。

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  run --rm --no-deps erp-api uv run --no-dev alembic upgrade head
```

预期：打出一串 `Running upgrade ... -> 20261012_0019`（head 以你仓库为准）。

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  run --rm --no-deps erp-api uv run --no-dev alembic current
```

权限目录（幂等，可重复，必须打 IAM）：

```bash
docker compose --env-file /opt/neorvion/env/.env.production \
  -f deploy/compose/docker-compose.production.yml \
  run --rm --no-deps iam-api uv run --no-dev python -m app.scripts.seed_permissions
```

**不要**自动 `seed_demo`。若这是作品演示机，先在 IAM 建用户与租户，再带 `DEMO_TENANT_ID` / `DEMO_USER_ID` / `DEMO_MEMBER_ID` 跑 ERP seed。

**【检查点：Backend】**

```bash
curl -sS http://127.0.0.1:8011/api/v1/health
curl -sS http://127.0.0.1:8011/api/crypto/public-key
```

预期：JSON `code=0`，`data.app=ok`，`mysql/redis` 为 `ok`（worker 需 worker 已起来才是 ok）。公钥接口返回 `public_key`，**没有**私钥。

`ss -lntp | grep 8011` 预期：`127.0.0.1:8011`，**不是** `0.0.0.0:8011`。

---

### 第十五阶段：部署 Shell / ERP 前端

生产服务器不装 Node。在【本地 Windows PowerShell】仓库根目录：

```powershell
pnpm install
$env:VITE_API_BASE_URL="https://neorvion.com"
$env:VITE_ERP_ENTRY="https://neorvion.com/erp"
pnpm --filter @neorvion/shell build
$env:VITE_PUBLIC_BASE="/erp/"
pnpm --filter @neorvion/erp build
```

若尚未备案、先用 IP 访问，把上面两个 URL 改成 `http://YOUR_SERVER_IP`（无证书时）。正式域名 + HTTPS 后再按 `https://neorvion.com` 重新构建一次。

上传【本地】（WinSCP 或 scp）：

- `apps/shell/dist/*` → 服务器 `/opt/neorvion/releases/first/shell/`
- `apps/erp/dist/*` → 服务器 `/opt/neorvion/releases/first/erp/`

【服务器 SSH / deploy】：

```bash
ln -sfn /opt/neorvion/releases/first/shell /opt/neorvion/current/shell
ln -sfn /opt/neorvion/releases/first/erp /opt/neorvion/current/erp
ls -l /opt/neorvion/current
ls /opt/neorvion/current/shell/index.html
ls /opt/neorvion/current/erp/index.html
```

Wujie：Shell 的 `VITE_ERP_ENTRY` 必须是 **生产 ERP 静态 Origin + `/erp`**，不能再是 `localhost:8016`。ERP `base=/erp/`，刷新 `/erp/orders` 由 Nginx 回 `erp/index.html`。

---

### 第十六–十七阶段：宝塔网站与 Nginx

【宝塔网页】网站 → 添加站点

- 域名：`neorvion.com`（可同时 `www.neorvion.com`）
- 根目录：可先用默认 `/www/wwwroot/neorvion.com`，保存后再把配置里的 `root` 改成 `/opt/neorvion/current/shell`
- PHP：纯静态 / 不创建
- **不要**让宝塔创建数据库

【宝塔网页】该站点 → 设置 → 配置文件：用仓库 `deploy/nginx/neorvion.conf` 的 `server { ... }` 替换（注意 `server_name`）。

【服务器 SSH / root】先测试再 reload：

```bash
/www/server/nginx/sbin/nginx -t
```

预期：`syntax is ok`、`test is successful`。失败则不要 reload。

```bash
/www/server/nginx/sbin/nginx -s reload
```

要点：

- `/api/v1/auth/`、`/api/v1/sessions`、`/api/v1/tenants`、`/api/v1/roles`、`/api/v1/permissions`、`/api/v1/users`、`/api/v1/applications`、`/api/v1/menus`、`/api/v1/audit-logs`、`/.well-known/`、`/api/crypto/` → `127.0.0.1:8010`（IAM）
- `/api/v1/knowledge-bases`、`/api/v1/documents`、`/api/v1/conversations`、`/api/v1/evaluation`、`/api/v1/search` 等 Knowledge 前缀 → `127.0.0.1:8012`
- 其余 `/api/` → `127.0.0.1:8011`（ERP），**禁止** try_files 到 index.html
- `/erp/` → ERP 静态，刷新不 404
- `/` → Shell History fallback
- 现在 **不要**加 `/api/agent/`（会 502）
- 参考仓库 `nginx/nginx.conf`，不要把整段 `/api/` 只指到 ERP

日志：宝塔网站 → 日志，或 `/www/wwwlogs/`。

---

### 第十八阶段：DNS

【腾讯云 DNSPod / 域名解析】

- A 记录 `@` → 服务器公网 IP
- A 记录 `www` → 同一 IP

若尚未备案：中国大陆机房可能无法用域名打开，可用 IP 测试，或等备案接入完成。本文不提供绕过备案的方法。

【备案检查】腾讯云控制台 → 备案。未完成前不要指望 `https://neorvion.com` 在大陆公网稳定打开。

---

### 第十九阶段：HTTPS

【宝塔网页】网站 → SSL → Let's Encrypt → 填邮箱与域名 → 申请 → 开启强制 HTTPS。

预期：浏览器锁标。证书续签由宝塔定时任务负责，在「计划任务」里应能看到 SSL 相关任务。

同域 `/api`：Refresh Cookie `Secure=true`、`HttpOnly`、`SameSite=lax`。不要 `*` CORS + credentials。

---

### 第二十阶段：业务验证

浏览器（替换成你的域名或 IP）：

1. 打开首页（Shell）
2. `/erp`、`/erp/products`、`/erp/orders` **直接刷新** 不能 404
3. `https://neorvion.com/api/v1/health`
4. 注册 / 登录（RSA 公钥正常）
5. 创建或选择租户 → Dashboard → 商品 / 仓库 / 库存 / 订单 主要页面能打开

【服务器 SSH / deploy】只读冒烟：

```bash
chmod +x /opt/neorvion/src/scripts/*.sh
/opt/neorvion/src/scripts/smoke-test-production.sh
```

【本机 PowerShell】确认外网端口（把 IP 换掉）：

```powershell
Test-NetConnection YOUR_SERVER_IP -Port 443
Test-NetConnection YOUR_SERVER_IP -Port 3306
Test-NetConnection YOUR_SERVER_IP -Port 6379
Test-NetConnection YOUR_SERVER_IP -Port 8011
```

预期：443 通；3306 / 6379 / 8011 **不通**。

【服务器】

```bash
ss -lntp
```

预期有 80/443/8888，以及 `127.0.0.1:8011`。不应有 `0.0.0.0:3306` / `5432` / `6379`。

第一次备份：

```bash
/opt/neorvion/src/scripts/backup-mysql.sh
ls /opt/neorvion/backups/mysql
```

**【可选】全部验证完再 reboot**（不要第一天一上来就重启）：

```bash
reboot
```

重登后：

```bash
systemctl status docker --no-pager
docker compose --env-file /opt/neorvion/env/.env.production \
  -f /opt/neorvion/src/deploy/compose/docker-compose.production.yml ps
curl -sS http://127.0.0.1:8011/api/v1/health
```

预期：Docker 自动起来，compose 服务 `unless-stopped` 仍在。

---

## B. 以后自动发布

1. 本地开发，你自己 commit、push `main`
2. CI（ruff / pytest / frontend test / build）
3. 把 `main` **PR 合入** `production`（不要 Cursor 自动 push）
4. `deploy-production.yml`：CI → 构建 GHCR SHA 镜像 → 构建前端 → SCP → SSH `deploy` → flock → 备份 MySQL → pull image → **Alembic** → compose up → health → 切前端符号链接

配置 Secrets 的逐步点击路径见 `docs/github-cicd.md`。

自动部署 **绝不**删除 `.env.production`，**绝不**自动 seed，**绝不** `docker compose down -v`。

---

## Backup / Restore / Rollback（摘要）

- 备份：`scripts/backup-mysql.sh`。密码在容器环境里，不出现在宿主机 `ps` 的 `-pPASSWORD`。
- Postgres 备份不是 ERP 必备：`scripts/backup-postgres.sh`
- 保留 14 天，脚本只删备份目录里的匹配文件
- **【危险操作】Restore**：先停 erp-api/worker，对 mysql 灌入 gunzip sql，再启动。步骤见 `docs/server-operations.md`
- 应用回滚：换上一个 **镜像 SHA**。`scripts/rollback-app.sh`。**不要**自动 `alembic downgrade`
- 代码回滚 ≠ 数据库回滚。Schema 不兼容时用备份恢复

---

## 2C2G 资源

当前 Compose 限制大约：MySQL 512M、Postgres 256M、Redis 160M、API 384M、Worker 256M。再加上宝塔 Nginx，内存会紧。必须有 Swap。若 idle 也长期 >80% 内存，升级 **2C4G**。不要为了省钱频繁 OOM。

API 1 个 uvicorn 进程，Worker 1 个。以后加机器再调。

---

## 未来 Agent（现在不要配 Nginx）

以后 Compose 可增加 `agent-api`，连 **Postgres+pgvector、Redis、ERP HTTP API**。Agent **禁止**直连改 ERP MySQL。Nginx 再加 `/api/agent/`。现在加了会 502。

---

## 第一次上线验收 Checklist

- [ ] OpenCloudOS 9.2 确认
- [ ] deploy 用户 + docker 组
- [ ] 专用 SSH Key（GitHub 不用 root）
- [ ] 腾讯云安全组：80/443；22 与 8888 限制自己的 IP；数据库端口关闭
- [ ] 宝塔改入口 / 强密码 / 尽量 IP 白名单
- [ ] Docker + Compose v2
- [ ] Swap
- [ ] 宝塔 Nginx（无宝塔 MySQL）
- [ ] 域名解析 / 备案状态已检查
- [ ] HTTPS（若域名可用）
- [ ] MySQL 8.4 healthy，应用用户非 root
- [ ] Redis 有密码 + AOF
- [ ] Postgres + `vector` 扩展
- [ ] `curl 127.0.0.1:8011/api/v1/health`
- [ ] Worker 心跳
- [ ] Alembic head
- [ ] Shell + ERP 静态，`/erp` 刷新不 404
- [ ] 登录 / 租户 / 主要页面
- [ ] 第一次 MySQL 备份
- [ ] `ss` 无 0.0.0.0:3306/5432/6379
- [ ] 外网测不通 3306/8011
- [ ] （可选）GitHub Secrets + production 分支 + 一次自动发布演练
- [ ] （可选）应用镜像回滚演练（不要 downgrade）
