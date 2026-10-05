# 仓库管理

当前里程碑 **V4**。Warehouse 表示企业的实际仓或逻辑仓，例如深圳一号仓、广州仓、美国洛杉矶海外仓、Amazon FBA-US-WEST。

本版只做仓库档案，不记账库存数量。后续库存不是 `SKU → quantity`，而是：

```text
Tenant + Warehouse + SKU → Inventory
```

V4 完成仓库档案。库存数量见 V5 `docs/inventory.md`。V4 **不**开发采购入库、销售出库、收货、发货、订单、物流。

## 在 ERP 中的作用

- 一个 Tenant 可以有 0 个或多个仓库。
- 所有仓库行都带 `tenant_id`。查询、更新、删除必须同时匹配 `id` 与 `tenant_id`。
- 仓库联系人是运营备注字段，不关联 `users` / `tenant_members`。
- 地址直接存在 `warehouses` 上：`country_code`（ISO 两位）、`province`、`city`、`address`。本版不做地图或省市区联动。

## 表结构

迁移：`backend/alembic/versions/20261003_0009_create_warehouses.py`

| 列 | 说明 |
| --- | --- |
| `id` | 自增主键 |
| `tenant_id` | 所属企业，外键 `tenants.id` |
| `name` | 名称 |
| `code` | 租户内唯一；创建时可空，flush 后写入 |
| `type` | `DOMESTIC` / `OVERSEAS` / `FBA` / `THIRD_PARTY` / `OTHER` |
| `country_code` | 可空，ISO 两位 |
| `province` / `city` / `address` | 可空 |
| `contact_name` / `contact_phone` | 可空，运营联系信息 |
| `is_default` | 是否默认仓 |
| `status` | `ACTIVE` / `DISABLED` |
| `remark` | 可空 |
| `created_at` / `updated_at` | 时间戳 |

约束：

- `UNIQUE(tenant_id, code)`
- `UNIQUE(tenant_id, id)`（给后续库存复合外键预留）
- 联合索引 `(tenant_id, status)`、`(tenant_id, type)`

MySQL 不便实现「每个租户最多一个 `is_default = true`」的部分唯一约束，默认仓由 Service 事务 + 行锁保证。

## 仓库编码

新增时 `code` 非必填。未填写时：

1. `session.add(warehouse)`，`code` 先为空
2. `session.flush()`，MySQL 分配自增 `id`
3. `code = f"WH{id:010d}"`，例如 `id=1` → `WH0000000001`
4. `commit`

不要用 `MAX(code)+1`：删除后会跳号复用，并发也不安全。`flush` 只把 INSERT 发给数据库并拿到 id，事务仍未提交；若后面 `IntegrityError`，`rollback` 会撤掉空编码行。

用户手动填写时保留自定义编码（规范化为大写），仍受 `UNIQUE(tenant_id, code)` 约束。不同租户可以有相同 `code`。

编辑已有仓库时 PATCH 不提交 `code`，保持原值，不能重新生成。前端编辑态编码只读。

## 仓库类型

数据库存稳定英文枚举；前端中文展示：

| 值 | 含义 | 界面 |
| --- | --- | --- |
| `DOMESTIC` | 国内自营仓 | 国内仓 |
| `OVERSEAS` | 海外仓 | 海外仓 |
| `FBA` | Amazon FBA 仓 | FBA |
| `THIRD_PARTY` | 第三方仓储 | 第三方仓 |
| `OTHER` | 其他 | 其他 |

## 默认仓库规则

1. 每个 Tenant 可以没有仓库。
2. 该租户的第一个仓库自动成为默认仓库，且必须是 `ACTIVE`。
3. 同一 Tenant 最多一个 `is_default = true`。
4. 默认仓库必须处于 `ACTIVE`。禁止 `is_default = true` 且 `status = DISABLED`。
5. 禁用默认仓库一律拒绝（`DEFAULT_WAREHOUSE_CANNOT_DISABLE`）。请先把其他启用仓库设为默认。
6. 删除默认仓库：若该租户还有其他仓库，拒绝（`DEFAULT_WAREHOUSE_CANNOT_DELETE`）；若它是最后一个仓库，允许删除。
7. 停用仓库不能被设为默认（`DISABLED_WAREHOUSE_CANNOT_SET_DEFAULT`）。

设置仓库 B 为默认时，同一事务内：旧默认 A `is_default = false`，B `is_default = true`，然后一次 `commit`。不能先提交 A 再改 B：中间窗口该租户会没有默认仓；第二步失败时旧默认已经没了。

## SELECT FOR UPDATE

`set_default_warehouse()` 会对当前租户全部仓库行 `SELECT ... FOR UPDATE ORDER BY id`。

两个管理员同时把 A、B 设为默认时，若不加锁，双方都可能先读到「当前默认是 C」，再各自把目标改成 true，最终出现两个默认仓。行锁让后到的事务等到前一个提交，再读到已更新的标记。按 `id` 排序避免死锁。`WHERE tenant_id = ?` 保证不会锁到或改到其他企业。

第一个仓库创建时表里还没有仓库行可锁，因此先锁 `tenants` 行，再判断 `count == 0`。这样两个「第一个仓库」不会同时把自己标成默认。不使用 Redis 分布式锁。

## 删除规则

已被库存或采购单引用的仓库不能物理删除（`WAREHOUSE_IN_USE`），只允许停用。必须二次确认。

## 多租户隔离

所有仓库 API 使用现有 `TenantContext` 与 `X-Tenant-ID`。Repository 查询条件始终包含 `tenant_id`。A 企业不能查看、修改、删除或设置 B 企业的仓库。

## 权限

| code | 用途 |
| --- | --- |
| `warehouse:read` | 列表 / 详情 / 菜单 |
| `warehouse:create` | 新增 |
| `warehouse:update` | 编辑档案、设为默认 |
| `warehouse:disable` | 启用 / 禁用 |
| `warehouse:delete` | 删除 |

不单独增加 `warehouse:set-default`。接口不按角色名称硬编码，只看 `role_permissions`。

默认模板：OWNER / ADMIN 全部；OPERATOR / VIEWER 只读；WAREHOUSE 角色可读、新增、编辑，默认不能停用或删除。历史租户在 `seed_permissions` 时 `backfill_existing_tenants`（系统角色只增不删）。

## API

均需登录和 `X-Tenant-ID`。

| 方法 | 路径 | 权限 |
| --- | --- | --- |
| GET | `/api/v1/warehouses` | `warehouse:read` |
| GET | `/api/v1/warehouses/{id}` | `warehouse:read` |
| POST | `/api/v1/warehouses` | `warehouse:create` |
| PATCH | `/api/v1/warehouses/{id}` | `warehouse:update` |
| PATCH | `/api/v1/warehouses/{id}/status` | `warehouse:disable` |
| POST | `/api/v1/warehouses/{id}/set-default` | `warehouse:update` |
| DELETE | `/api/v1/warehouses/{id}` | `warehouse:delete` |

列表支持 `q`（名称/编码）、`type`、`status`、分页。

## 前端

路由：`/warehouses`，权限 `warehouse:read`，页面为列表 + Drawer，不单独做复杂详情页。

Query Key：

```ts
['tenant', tenantId, 'warehouses', params]
['tenant', tenantId, 'warehouse', warehouseId]
```

新增 / 编辑 / 删除 / 设默认 / 启停后 invalidate 上述 key。租户切换沿用现有 Query 隔离。
