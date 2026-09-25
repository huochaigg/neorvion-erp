# API 说明

统一响应：

```json
{
  "code": 0,
  "message": "ok",
  "data": {}
}
```

`code = 0` 表示成功。业务错误走 `AppError`，返回非 0 的 `code`。

## M1 接口

### `GET /api/v1/health`

用途：探活应用、MySQL、Redis。

输入：无。

输出：

```json
{
  "code": 0,
  "message": "ok",
  "data": {
    "app": "ok",
    "mysql": "ok",
    "redis": "ok",
    "milestone": "M1"
  }
}
```

规则：依赖不可用时 HTTP 仍为 200，`mysql` / `redis` 标记为 `unavailable`。

Swagger：http://localhost:8001/docs

认证、租户、业务接口从 M2 开始补充。
