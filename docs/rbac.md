# RBAC 权限模型（V2.3.1 ~ V7）

V2.3.1 完成后端权限基础设施。V2.3.2 完成企业成员授权与 ERP 管理页面。V2.3.3 完成动态权限菜单、页面守卫与按钮权限。V2.3.4 补全成员/角色 CRUD、代建账号、角色权限配置与权限目录。V2.3.5 补齐企业内成员名称、细粒度系统管理权限、菜单按钮权限树，并结束 V2 RBAC 基础设施。V3 商品模块沿用 `product:read/create/update/delete`，类目和品牌不另拆编码。V4 新增 `warehouse:read/create/update/disable/delete`，设默认仓归 `warehouse:update`。V5 新增 `inventory:initialize` / `inventory:adjust` / `inventory:transaction:read`，保留预留的 `inventory:inbound` / `inventory:outbound`。V6 补齐 `purchase:update/submit/cancel` 与独立 `supplier:*`。V7 补齐 `order:update/submit` 与独立 `customer:*`，确认沿用已有 `order:audit`。V8 新增 `purchase:receipt:read/create/update/confirm/cancel` 与 `outbound:read/create/pick/confirm/cancel`。V9 新增 `carrier:read/create/update/disable/delete` 与 `shipment:read/create/update/confirm/tracking:update/deliver/cancel`。V10 新增 `stocktake:read/create/update/submit/confirm/cancel` 与 `stock_transfer:read/create/update/submit/outbound/receive/cancel`。业务确认不要求再同时拥有 `inventory:inbound` / `inventory:outbound`。详见 `docs/versions/v10.md`、`docs/stocktake.md` 与 `docs/stock-transfer.md`。

## 关系：User、TenantMember、Role、Permission

```text
User（全局人）
  └── TenantMember（这个人在这家企业的身份）
        └── MemberRoleGrant（member_roles）
              └── Role（这家企业自己的角色）
                    └── RolePermission（role_permissions）
                          └── Permission（平台统一权限目录）
```

- **User**：邮箱和密码、全局 `display_name`。没有 `tenant_id`，一个人可以加入多家企业。
- **TenantMember**：某用户在某企业里是否有效。可选 `display_name` 只影响当前企业展示，空则回退 `User.display_name`。`tenant_members.role` 仍表示所有权（OWNER / MEMBER），**不是**细粒度权限。
- **Role**：属于具体租户。Acme 的 `ADMIN` 和 Beta 的 `ADMIN` 是两行。
- **Permission**：平台统一定义的操作编码，例如 `tenant:member:create`。`PermissionCode` 表示代码真实支持的能力，不是某个角色的固定清单。
- **RolePermission**：某个租户角色实际拥有哪些目录项。

最终权限 = 当前租户下该成员所有有效角色权限的 **并集**。OWNER 列另外表示所有权：目录里已登记的权限，所有者全部拥有。

不要把角色写进 `users` 表。不要用全局用户角色代替租户角色。企业管理员不能通过成员接口改邮箱、密码或 User 全局名称。

最终权限 = 当前租户下该成员所有有效角色权限的 **并集**。OWNER 列另外表示所有权：目录里已登记的权限，所有者全部拥有。

不要把角色写进 `users` 表。不要用全局用户角色代替租户角色。

## 为什么角色需要 tenant_id

角色是企业私有配置。货代 A 的「仓库主管」和卖家 B 的「仓库主管」权限不同，也不能把 A 的角色授给 B 的员工。

`UNIQUE(tenant_id, code)`：同一企业角色编码不重复；不同企业可以都叫 `ADMIN`。

查询、更新、删除角色时必须带已校验的 `TenantContext.tenant_id`。只凭 URL 里的 `role_id` 会越权读到别的企业。

## 为什么 Permission 可以统一定义

`tenant:member:create` 对所有企业含义相同：在本企业添加成员。没有必要每家企业复制一份权限表。

租户不能 CRUD 权限目录。用户自行创建的 code 若从未被 `require_permission` 使用，则没有任何实际意义。未知 code 是服务端配置错误（`50021`），不能悄悄放行。

角色授权界面是程序定义的 DIRECTORY → MENU → ACTION 树（`GET /api/v1/permissions/tree`）。树只是 UI；真正授权仍写入 `role_permissions`。React 路由由 `routes.ts` 驱动，不能由租户在数据库里随便新增前端页面。

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
    context: Annotated[TenantContext, Depends(require_permission(PermissionCode.TENANT_ROLE_CREATE))],
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
| 系统角色 | `is_system=True`。OWNER 权限冻结；ADMIN 等可调业务权限但不能删除 | 自定义角色可以改、可以删（仍被使用则禁止删） |
| 最后一个 | 不能禁用 / 不能卸掉最后一个有效 OWNER | 不涉及所有权 |
| 授予 | 创建租户和历史回填自动授予；普通分配接口不能授予 | 后续成员分配页处理 |

OWNER 转移是独立业务流程，本版本不做。

旧字段 `Tenant.created_by` 和 `TenantMember.role` **保留**。迁移会给历史 OWNER 成员补上 `OWNER` 角色，给其他成员补上 `VIEWER`，避免老管理员突然没权限。

## 角色权限变更为什么需要事务

替换权限的步骤是：校验 permission_id 都存在 → 校验角色属于当前租户 → OWNER 拒绝修改；ADMIN 必须保留租户管理编码 → 删除旧关联 → 插入新关联。

任一步失败必须 `rollback`，否则会出现「旧权限删了、新权限只写了一半」。Repository 禁止 `commit`，由 Service 提交。

创建租户同样在一个事务里完成：Tenant → OWNER 成员 → 默认角色 → 创建者挂 OWNER 角色。角色初始化失败会整单回滚，不会留下半成品企业。

## 为什么前端隐藏按钮不能代替后端权限校验

前端可以藏「删除角色」按钮，攻击者仍能直接发 `DELETE /api/v1/roles/{id}`。浏览器不是安全边界。授权必须在服务端按当前租户成员关系计算。

## 默认角色模板

| 角色 | 说明 | 权限要点 |
| --- | --- | --- |
| OWNER | 所有者 | 目录中全部权限；另有所有权语义 |
| ADMIN | 管理员 | 目录中全部权限（不含所有权） |
| OPERATOR | 运营 | 商品/订单/采购日常操作，只读仓库、客户和供应商；不能确认销售订单，不能管成员和角色 |
| WAREHOUSE | 仓库 | 维护仓库档案，入出库，只读商品、订单、供应商与采购单；默认不能停用或删除仓库，也没有客户档案权限 |
| VIEWER | 只读 | 各模块 read |

新加入的普通成员默认授予 **VIEWER**。

## API

都需要登录。角色与权限接口还需要有效 `X-Tenant-ID`。

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/permissions` | `tenant:permission:read` 或 `tenant:role:read` |
| GET | `/api/v1/permissions/tree` | 同上 |
| GET | `/api/v1/roles` | `tenant:role:read` |
| POST | `/api/v1/roles` | `tenant:role:create` |
| GET | `/api/v1/roles/{role_id}` | `tenant:role:read` |
| PATCH | `/api/v1/roles/{role_id}` | `tenant:role:update`（仅自定义角色的 name/description；code 只读） |
| PUT | `/api/v1/roles/{role_id}/permissions` | `tenant:role:permission:update` |
| DELETE | `/api/v1/roles/{role_id}` | `tenant:role:delete` |

系统角色删除 → `40040`。OWNER 改权限 → `40040`。ADMIN 拿掉租户管理能力 → `40040`。角色仍被成员使用 → `40041`，`data.error = ROLE_IN_USE`，含 `member_count`。跨租户 `role_id` → `40420`。旧 `tenant:role:manage` / `tenant:member:manage` 保留兼容，新接口按细粒度校验。

成员管理（路径参数 `tenant_id` 必须等于 `X-Tenant-ID`）：

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/tenants/{tenant_id}/members` | `tenant:member:read` |
| POST | `/api/v1/tenants/{tenant_id}/members` | `tenant:member:create`（已有账号） |
| POST | `/api/v1/tenants/{tenant_id}/members/accounts` | `tenant:member:create`（代建账号） |
| GET | `/api/v1/tenants/{tenant_id}/members/{member_id}` | `tenant:member:read` |
| GET | `/api/v1/tenants/{tenant_id}/members/{member_id}/permissions` | `tenant:member:read` |
| PUT | `/api/v1/tenants/{tenant_id}/members/{member_id}/roles` | `tenant:member:role:update` |
| PATCH | `/api/v1/tenants/{tenant_id}/members/{member_id}` | `tenant:member:update`（企业内名称）和/或 `tenant:member:disable`（启用/禁用） |
| DELETE | `/api/v1/tenants/{tenant_id}/members/{member_id}` | `tenant:member:remove`（移出企业，不删 User） |

`GET /api/v1/tenants/current` 返回 `permission_codes`。  
`GET /api/v1/tenants/current/my-permissions` 返回当前成员 `roles` 与 `permissions` 编码数组。两者都每次查库，不信任前端提交的权限列表。

前端菜单、页面守卫和按钮只读取 React Query 中的当前租户权限。隐藏按钮不能代替上表的服务端校验。

添加已有账号请传已注册用户的 `email` 和可选 `role_ids`。代建账号请传 `display_name`、`email`、可选 `role_ids`，响应中的 `temporary_password` 只出现一次。不能授予 OWNER。默认角色为 VIEWER。禁用保留成员行；移除删除 TenantMember 与 MemberRoleGrant，不删 User。

ERP 系统管理页：成员管理、角色管理、权限目录（只读）。角色权限用 Ant Design Tree 勾选菜单与按钮，提交 `permission_ids`。

幂等灌入权限目录（不删已有行，并展开旧 manage）：

```bash
cd backend
uv run python -m app.scripts.seed_permissions
```

不要在应用启动时建表。建表只走 Alembic：`20260926_0004`（RBAC 表）、`20260928_0005`（`users.must_change_password`）、`20260928_0006`（`tenant_members.display_name` 与细粒度权限 seed）。
