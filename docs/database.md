# 数据库说明

V1 使用 **共享 MySQL + 共享业务表 + tenant_id**，不用每租户独立库。

当前里程碑 M1 **尚未创建业务表**。Alembic 已初始化，初始 revision `20260925_0001` 为空，仅用于打通迁移命令。

M2 将创建：

- `users`、`tenants`、`tenant_members`
- `roles`、`permissions`、`member_roles`、`role_permissions`

M3 起创建商品、仓库、库存等表。所有业务表必须包含 `tenant_id`，唯一约束必须带上租户，例如：

```sql
UNIQUE (tenant_id, sku_code)
UNIQUE (tenant_id, warehouse_id, sku_id)
```

正式建表只通过 Alembic，不在运行时 `create_all`。

连接配置见 `.env.example`。SQLAlchemy 2.x 使用同步 `Session`，便于后续 `SELECT ... FOR UPDATE` 库存锁。
