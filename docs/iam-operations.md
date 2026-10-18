# IAM V2 权限配置、会话与故障处理

本文描述**当前代码真实行为**，不是目标架构。状态标记与手册一致。

## 权限配置【已实现】

1. 权限目录在 IAM `permissions` 表，编码全局唯一。真实码如 `order:read`、`knowledge:create`、`iam:users:read`。
2. 业务服务启动后可用 `POST /api/v1/internal/permissions/sync`（`X-Permission-Sync-Key`）做确定性 UPSERT：更新名称/说明/模块，**不修改** `role_permissions`。
3. 管理员在 `apps/iam`：
   - 应用注册：启停应用、查看 audience
   - 角色管理：按权限树勾选（可搜索编码），查看成员数；停用自定义角色后该角色权限不再计入并集
   - 成员管理：一人多角色；跨应用权限是角色并集
   - 菜单管理：目录/页面/按钮绑定 `permission_code`。**菜单隐藏不是 API 授权**
4. 平台超级管理员（`is_platform_admin`）与租户 OWNER / ADMIN / 普通成员分离。没有公开接口把普通用户提权为平台管理员；引导脚本读环境变量 `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`。

## 会话管理【已实现】

1. 登录写入 `auth_sessions`：`public_id` 进入 JWT `sid`，Refresh **jti 只存 SHA-256**。
2. `GET /api/v1/sessions` 列出当前用户设备、创建/最近活动/失效时间、撤销状态。
3. `DELETE /api/v1/sessions/{id}` 撤销指定会话；`POST /api/v1/sessions/revoke-all` 退出全部设备并递增 token_version。
4. Refresh 轮换：当前 jti 不匹配且命中 previous/family 视为重放，撤销整族并 401。
5. Access Token 仍短期有效。已撤销会话的 **IAM 请求与高风险权威授权** 会查会话表拒绝。普通 ERP 读接口在 Access 过期前仍可能成功，这是设计边界，不是漏洞声明成「立即全局失效」。

内部 SSO，**不是**标准 OIDC。【未实现】authorize / id_token / 企业 IdP。

## 故障与撤权边界

| 场景 | 普通接口 | 高风险接口 |
| --- | --- | --- |
| Redis 快照缺失或 aver 不一致 | 403 / 503，fail-closed | 回源 IAM 数据库 |
| Redis 宕机 | 拒绝 | IAM 库 + 会话表仍可判定；IAM 也不可达则拒绝 |
| IAM 宕机 | 已缓存 JWKS 可验未过期 Access；Refresh 失败退出 | 权威授权 503，拒绝 |
| DB 已提交、Redis 未刷新即崩溃 | 最长约快照 TTL（默认 3600s）可能仍用旧权限 | 权威授权读库，无此窗口 |
| ERP Worker | 必须 `load_for_principal` 使用创建者快照，禁止空身份 | 报表导出校验对应 analytics 权限 |

【未实现】跨 Redis/MySQL 的两阶段提交，因此**不能**声称普通接口强一致撤权。

开发环境未配置 `IAM_INTERNAL_KEY` 时，ERP/Knowledge 高风险依赖 Redis 快照并标记 `snapshot-dev`，仅供测试。**生产必须配置** `IAM_AUTHORIZE_URL` 与 `IAM_INTERNAL_KEY`。
