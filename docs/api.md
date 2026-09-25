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

依赖不可用时 HTTP 仍为 200，字段标记 `unavailable`。当前 `milestone` 为 `V2.1.2`。

## 认证

详见 `docs/auth.md`。

- `GET /api/crypto/public-key`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`

Swagger：http://localhost:8011/docs
