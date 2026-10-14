# Python 与 FastAPI 内部备忘

适合检索的技术说明。针对本仓库 Knowledge 服务的习惯，不是 Python 官方教程全文。

## FastAPI

- 路由通过 `APIRouter` 注册，统一前缀 `/api/v1`。
- 依赖注入：`Annotated[AsyncSession, Depends(get_db)]`。
- 响应包一层 `ApiResponse`，**`code=0` 表示成功**。
- 上传文件使用 `UploadFile`；为避免 B008，用 `Annotated[UploadFile, File()]`，不要用裸 `File(...)`。
- Pydantic v2：字段加 `description`，`extra=forbid` 防止客户端改 `tenant_id` 等不允许字段。请求体多了不允许字段通常返回 **422**。

## 异步 SQLAlchemy 2.0

**Repository 不 `commit`。** Service 负责提交。查询必须带 `tenant_id`。写法：`select(Model).where(Model.tenant_id == tenant_id, ...)`。

## 常见排查

- 422：请求体多了不允许的字段。
- 401：缺 Bearer 或 JWT 无效。
- 403：权限码不足。
- 404：资源不存在或不属于当前租户，二者对外都是不可访问，避免泄露资源是否存在。
