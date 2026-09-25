# 认证说明（V2.1）

本阶段只实现全局用户身份与 JWT，不实现租户和 RBAC。`users` 表没有 `tenant_id`，也没有角色字段。

## 数据模型

`users`

| 字段 | 说明 |
| --- | --- |
| id | 主键 |
| email | 唯一，存储前转小写 |
| password_hash | Argon2id 存储哈希，接口永不返回 |
| display_name | 显示名称 |
| status | `ACTIVE` / `DISABLED` |
| last_login_at | 最近登录 |
| created_at / updated_at | 时间戳 |

## 令牌设计

- Access Token：30 分钟，响应 JSON 返回，前端只放内存。
- Refresh Token：7 天，HttpOnly Cookie，`Path=/api/v1/auth`，开发环境 `SameSite=Lax`、`Secure=false`；生产环境强制 `Secure`。
- Payload：`sub`、`type`（access/refresh）、`iat`、`exp`、`jti`。
- Redis 键：`auth:refresh:{jti}`，值为 user_id。退出或刷新轮换时删除旧 jti。

Refresh Token 不能当作 Access Token 访问 `/me`。

## 密码保护

不使用 MD5。MD5 太快，也不抗碰撞，不适合保护口令。

实际分两层：

1. **传输**：前端用 Web Crypto 计算 `SHA-256(明文)`，请求体只发 64 位小写十六进制。开发者工具里看不到原始密码。
2. **存储**：后端对摘要再做 Argon2id，写入 `password_hash`。即使数据库泄露，也无法还原密码。

登录时前端同样先 SHA-256，后端用 Argon2id 校验。明文强度（8-72 位、字母+数字）仍在注册页校验。

## API

前缀：`/api/v1/auth`

| 方法 | 路径 | 说明 | 鉴权 |
| --- | --- | --- | --- |
| POST | /register | 注册 | 否 |
| POST | /login | 登录 | 否 |
| POST | /refresh | 刷新 Access Token | Refresh Cookie |
| POST | /logout | 撤销 Refresh 并清 Cookie | Refresh Cookie（可空） |
| GET | /me | 当前用户 | Access Token |

统一响应仍是 `{ code, message, data }`。

## 前端流程

1. 打开应用时调用 `/refresh` 尝试恢复登录。
2. 无有效 Cookie 则停在登录页。
3. 登录成功后内存保存 Access Token，并跳转原目标页。
4. 业务请求自动带 `Authorization: Bearer`。
5. 多个请求同时 401 时共用同一个 Refresh Promise，避免并发重复刷新。
6. Refresh 失败则清空状态并跳转 `/login`。
7. ERP 不实现登录页，只通过 Wujie props 接收 token 与用户快照。

## 环境变量

见 `backend/.env.example`。至少需要：

- `SECRET_KEY`
- `JWT_ACCESS_EXPIRE_MINUTES`
- `JWT_REFRESH_EXPIRE_DAYS`
- `MYSQL_*`（库名使用 `neorvion_erp`，测试库 `neorvion_erp_test`）
- `REDIS_*`

不要把真实密钥写进文档或提交 `.env`。

## 测试

```bash
cd backend
uv run pytest
```

测试会创建并使用独立数据库 `neorvion_erp_test`，以及 Redis DB 15。
