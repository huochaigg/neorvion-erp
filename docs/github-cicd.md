# GitHub CI/CD

本文件说明 **production 分支之后** 的自动发布。第一次上线请先按 `docs/deployment-production.md` 手工做完。

Cursor **不会**帮你创建或 push `production` 分支。

## 分支

| 分支 | 用途 |
| --- | --- |
| `main` | 日常稳定开发 |
| `production` | 线上发布。push 到这里才会 Deploy |

推荐流程：feature → PR 到 `main` → CI 通过 → 再把 `main` 合入 `production`。

【本地 Windows PowerShell】第一次创建 production（确认 main 已是你想上线的提交）：

```powershell
git checkout main
git pull
git checkout -b production
git push -u origin production
```

预期：GitHub 出现 `production` 分支。

## 保护 production

【GitHub 网站】仓库 → Settings → Rules → Rulesets → New branch ruleset

- Target：`production`
- Restrict force pushes
- Require a pull request before merging（个人项目可以不强制 reviewer）
- Require status checks to pass：勾选 `backend` / `frontend`（workflow 跑通后才会出现 check 名）

不要允许随便 force push。

## Workflows

仓库内：

- `.github/workflows/ci.yml`：PR 与 `main`。backend ruff + pytest（MySQL 8.4 + Redis 服务），frontend test + build。`pnpm lint` 目前 ESLint 10 有历史债，**不阻断**。
- `.github/workflows/deploy-production.yml`：仅 `production`。先复用 CI，再构建并推送 GHCR，SCP 前端，SSH 调用 `scripts/deploy-production.sh`。

权限：`contents: read`，deploy 额外 `packages: write`。没有 `write-all`。

镜像：

```text
ghcr.io/<owner>/<repo>/erp-api:<git-sha>
ghcr.io/<owner>/<repo>/erp-api:production-latest
```

生产以 **commit SHA** 为准，不要只部署 `latest`。

## Environment 与 Secrets

【GitHub 网站】Settings → Environments → New environment → 名称 `production`

Settings → Secrets and variables → Actions，或该 Environment 的 Secrets：

| Name | 放哪 | 含义 |
| --- | --- | --- |
| `PROD_HOST` | Environment secret | 服务器公网 IP 或 SSH 域名 |
| `PROD_USER` | Environment secret | 必须是 `deploy`，不要 root |
| `PROD_SSH_PRIVATE_KEY` | Environment secret | 专门的 deploy 私钥全文 |
| `PROD_DOMAIN` | Variable | 例如 `neorvion.com`，给 Vite 构建 |
| `PROD_SSH_PORT` | Variable | 默认 22 |

**不要**把 `MYSQL_PASSWORD`、JWT、RSA 私钥放进 GitHub。它们只留在服务器 `/opt/neorvion/env/.env.production`。

自动部署 **不会**覆盖该文件。

## 服务器拉 GHCR 私有镜像

若仓库/Package 是私有的，在服务器创建（chmod 600）：

`/opt/neorvion/env/ghcr.login`

```text
YOUR_GITHUB_USERNAME
ghp_xxx_read_packages_only
```

PAT 权限只要 `read:packages`。Deploy 脚本会 `docker login`，不会把 token echo 到日志。

## 并发

- GitHub：`concurrency: production-deploy`，`cancel-in-progress: false`（避免杀掉进行中的 Migration）
- 服务器：`flock /opt/neorvion/deploy.lock`

## 失败先看什么

| 现象 | 先看 |
| --- | --- |
| CI 红 | 对应 job 日志：pytest / pnpm build |
| Docker build 失败 | Dockerfile、uv.lock、context=backend |
| GHCR push 失败 | packages:write、login、镜像名是否含大写仓库名 |
| SSH 失败 | PROD_HOST / deploy 用户 / 公钥 / 安全组 22 |
| SCP 失败 | 磁盘、`/opt/neorvion/staging` 权限 |
| Backup 失败 | mysql 容器是否 healthy |
| Migration 失败 | `alembic current/heads`，不要乱 merge |
| Health 失败 | `docker compose logs erp-api` |
| Nginx 502 | `curl 127.0.0.1:8011/api/v1/health` |

更细的排障见 `docs/server-operations.md`。
