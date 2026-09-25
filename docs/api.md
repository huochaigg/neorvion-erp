# API 说明

统一响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

`code = 0` 表示成功。业务错误走 `AppError`。

## 健康检查

`GET /api/v1/health`

依赖不可用时 HTTP 仍为 200，字段标记 `unavailable`。当前 `milestone` 为 `V2.2.1`。

## 认证

详见 `docs/auth.md`。

- `GET /api/crypto/public-key`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

## 租户

详见 `docs/multi-tenancy.md`。除「创建 / 我的列表」外，租户业务接口使用请求头 `X-Tenant-ID`。

- `POST /api/v1/tenants`
- `GET /api/v1/tenants`
- `GET /api/v1/tenants/current`（需要 `X-Tenant-ID`）
- `GET /api/v1/tenants/{tenant_id}`
- `GET /api/v1/tenants/{tenant_id}/members`
- `POST /api/v1/tenants/{tenant_id}/members`
- `PATCH /api/v1/tenants/{tenant_id}/members/{member_id}`

Swagger：http://localhost:8011/docs
