# 数据库说明

使用 **共享 MySQL + 共享业务表 + tenant_id**，不用每租户独立库。

当前里程碑 V2.3.1 已创建：

- `users`：全局用户身份，**没有** `tenant_id`
- `tenants`：企业；`code` 唯一，不用名称当唯一键
- `tenant_members`：用户与企业的多对多；`UNIQUE(tenant_id, user_id)`；另有 `UNIQUE(tenant_id, id)` 供 RBAC 复合外键
- `permissions`：平台权限目录；`UNIQUE(code)`
- `roles`：租户角色；`UNIQUE(tenant_id, code)`
- `member_roles`：成员与角色；复合外键保证同一租户
- `role_permissions`：角色与权限

当前里程碑 V2.3.4 增加：

- `users.must_change_password`：管理员代建账号后必须改密

V2.3.3 完成动态权限菜单，不新增表。OWNER 转移留到后续独立流程。M3 起创建商品、仓库、库存等表。所有业务表必须包含 `tenant_id`（`TenantMixin`），唯一约束必须带上租户，例如：

```sql
UNIQUE (tenant_id, sku_code)
UNIQUE (tenant_id, warehouse_id, sku_id)
```

正式建表只通过 Alembic，不在运行时 `create_all`。

连接配置见 `.env.example`。SQLAlchemy 2.x 使用同步 `Session`，便于后续 `SELECT ... FOR UPDATE` 库存锁。
