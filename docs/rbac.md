# RBAC 权限模型（V2.3.1）

本阶段只做 **数据库模型、权限目录、默认角色、FastAPI 权限 Depends 和角色管理 API**。

不做：前端权限菜单、成员角色分配页面、OWNER 转移流程、商品/订单/库存业务。

## 关系：User、TenantMember、Role、Permission

```text
User（全局人）
  └── TenantMember（这个人在这家企业的身份）
        └── MemberRoleGrant（member_roles）
              └── Role（这家企业自己的角色）
                    └── RolePermission（role_permissions）
                          └── Permission（平台统一权限目录）
```

- **User**：邮箱和密码。没有 `tenant_id`，一个人可以加入多家企业。
- **TenantMember**：某用户在某企业里是否有效。`tenant_members.role` 仍表示所有权（OWNER / MEMBER），**不是**细粒度权限。
- **Role**：属于具体租户。Acme 的 `ADMIN` 和 Beta 的 `ADMIN` 是两行。
- **Permission**：平台统一定义的操作编码，例如 `tenant:member:manage`。

最终权限 = 当前租户下该成员所有有效角色权限的 **并集**。OWNER 列另外表示所有权：目录里已登记的权限，所有者全部拥有。

不要把角色写进 `users` 表。不要用全局用户角色代替租户角色。

## 为什么角色需要 tenant_id

角色是企业私有配置。货代 A 的「仓库主管」和卖家 B 的「仓库主管」权限不同，也不能把 A 的角色授给 B 的员工。

`UNIQUE(tenant_id, code)`：同一企业角色编码不重复；不同企业可以都叫 `ADMIN`。

查询、更新、删除角色时必须带已校验的 `TenantContext.tenant_id`。只凭 URL 里的 `role_id` 会越权读到别的企业。

## 为什么 Permission 可以统一定义

`tenant:member:manage` 对所有企业含义相同：管理本企业成员。没有必要每家企业复制一份权限表。

V2.3 不开放租户自建任意权限编码。未知 code 是服务端配置错误（`50021`），不能悄悄放行。

## 多对多关联表

`member_roles` 和 `role_permissions` 做成显式模型，因为它们自己有 `tenant_id` 和 `created_at`。不要用 `secondary=` 一张光秃秃的关联表，否则很难加复合外键。

`member_roles` 用复合外键同时指向：

- `(tenant_id, member_id) → tenant_members(tenant_id, id)`
- `(tenant_id, role_id) → roles(tenant_id, id)`

即使应用层写错，MySQL 也会拒绝「把租户 A 的成员挂到租户 B 的角色」。这就是为什么还要给 `roles` 和 `tenant_members` 增加 `UNIQUE(tenant_id, id)`：InnoDB 的复合外键要求被引用列上有匹配的唯一索引。

`role_permissions` 只对角色做租户复合外键。`permission_id` 指向全局 `permissions.id`，不必绑租户。

## SQLAlchemy relationship 和 selectinload

`relationship` + `back_populates` 让 Python 里能写 `role.role_permissions`，两端必须互指，否则会被当成两套单向关系。

不要用 `lazy="joined"` 把所有关联一次性 JOIN 进来：角色列表会变成笛卡尔积，成员权限树也会膨胀。

本阶段：

- 角色详情：`selectinload(Role.role_permissions).selectinload(RolePermission.permission)`
- 当前权限：JOIN `member_roles` → `role_permissions` → `permissions.code`，只取编码集合

`selectinload` 会再发一条 `IN (...)` 查询，而不是把主查询变成巨大 JOIN。

## FastAPI Depends 权限校验流程

```python
@router.post("/roles")
def create_role(
    payload: RoleCreate,
    context: Annotated[TenantContext, Depends(require_permission(PermissionCode.TENANT_ROLE_MANAGE))],
    session: DbSession,
):
    ...
```

依赖链：

1. `get_current_user`：解析 Access Token。失败 → **401**。
2. `get_tenant_context`：读 `X-Tenant-ID`，查 `tenant_members`。不是成员 → **404**；成员或企业禁用 → **40310**。
3. `require_permission(...)`：查当前成员角色权限并集。缺少权限 → **40320**。未知权限编码 → **50021**。

不要信任 JWT 里缓存的角色列表，也不要让前端在 body 里提交「我有哪些权限」。禁用成员、禁用租户、改角色权限后，下一次请求以数据库为准。

HTTP 层 Depends 挡不住后续 Agent / Celery 直接调 Service。敏感操作要走 `AuthorizationService.require_all_for_user(user_id=..., tenant_id=..., codes=...)`，先还原成员身份再判权。

## OWNER 与普通角色的区别

| | OWNER | ADMIN 等普通角色 |
| --- | --- | --- |
| 来源 | `tenant_members.role = OWNER`，并挂上系统角色 `OWNER` | 只通过 `member_roles` |
| 语义 | 企业所有权 | 可配置的岗位权限 |
| 系统角色 | `is_system=True`，角色 API 不能改权限、不能删除 | 自定义角色可以改、可以删（仍被使用则禁止删） |
| 最后一个 | 不能禁用 / 不能卸掉最后一个有效 OWNER | 不涉及所有权 |
| 授予 | 创建租户和历史回填自动授予；普通分配接口不能授予 | 后续成员分配页处理 |

OWNER 转移是独立业务流程，本版本不做。

旧字段 `Tenant.created_by` 和 `TenantMember.role` **保留**。迁移会给历史 OWNER 成员补上 `OWNER` 角色，给其他成员补上 `VIEWER`，避免老管理员突然没权限。

## 角色权限变更为什么需要事务

替换权限的步骤是：校验 permission_id 都存在 → 校验角色属于当前租户 → 系统角色拒绝修改 → 删除旧关联 → 插入新关联。

任一步失败必须 `rollback`，否则会出现「旧权限删了、新权限只写了一半」。Repository 禁止 `commit`，由 Service 提交。

创建租户同样在一个事务里完成：Tenant → OWNER 成员 → 默认角色 → 创建者挂 OWNER 角色。角色初始化失败会整单回滚，不会留下半成品企业。

## 为什么前端隐藏按钮不能代替后端权限校验

前端可以藏「删除角色」按钮，攻击者仍能直接发 `DELETE /api/v1/roles/{id}`。浏览器不是安全边界。授权必须在服务端按当前租户成员关系计算。

## 默认角色模板

| 角色 | 说明 | 权限要点 |
| --- | --- | --- |
| OWNER | 所有者 | 目录中全部权限；另有所有权语义 |
| ADMIN | 管理员 | 目录中全部权限（不含所有权） |
| OPERATOR | 运营 | 商品/订单/采购日常操作，不能管成员和角色 |
| WAREHOUSE | 仓库 | 入出库，只读商品与订单 |
| VIEWER | 只读 | 各模块 read |

新加入的普通成员默认授予 **VIEWER**。

## API

都需要登录。角色与权限接口还需要有效 `X-Tenant-ID`。

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/permissions` | `tenant:role:read` |
| GET | `/api/v1/roles` | `tenant:role:read` |
| POST | `/api/v1/roles` | `tenant:role:manage` |
| GET | `/api/v1/roles/{role_id}` | `tenant:role:read` |
| PATCH | `/api/v1/roles/{role_id}` | `tenant:role:manage` |
| PUT | `/api/v1/roles/{role_id}/permissions` | `tenant:role:manage` |
| DELETE | `/api/v1/roles/{role_id}` | `tenant:role:manage` |

系统角色修改/删除 → `40040`。角色仍被成员使用 → `40041`。跨租户 `role_id` → `40420`。

幂等灌入权限目录（不删已有行）：

```bash
cd backend
uv run python -m app.scripts.seed_permissions
```

不要在应用启动时建表。建表只走 Alembic：`20260926_0004`。
