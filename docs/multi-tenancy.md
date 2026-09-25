# 多租户说明（V2.2.1）

本阶段只做 **共享 MySQL + 共享业务表 + tenant_id**。不做每租户独立库、独立 Schema、微服务或完整 RBAC。

## users 和 tenant_members 为什么要分开

`users` 表示「这个人是谁」：邮箱、密码哈希、显示名。一个人可以同时在多家货代/卖家企业里干活。

如果把 `tenant_id` 写进 `users`，就会变成「一个账号只能属于一家企业」。换企业只能再注册，SaaS 做不到。

`tenant_members` 表示「这个人在哪家企业、什么身份、是否还有效」。多对多的关系放在中间表：

- 一个 user 多行 member → 加入多家企业
- 一个 tenant 多行 member → 一家企业多名员工
- `UNIQUE(tenant_id, user_id)` → 同一人不能重复加入同一家

JWT 只证明「你是这个 user_id」。进哪家企业要再查 `tenant_members`。

## 多对多在 SQLAlchemy 里怎么写

没有直接用 `secondary=` 的 association table，而是把中间表做成完整实体 `TenantMember`（带 status、role、joined_at）。这叫 **association object**。

```python
class Tenant:
    members: Mapped[list[TenantMember]] = relationship(back_populates="tenant")

class TenantMember:
    tenant: Mapped[Tenant] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")

class User:
    memberships: Mapped[list[TenantMember]] = relationship(back_populates="user")
```

`relationship` 让你用 `tenant.members` 这种 Python 属性访问对方，而不用手写 JOIN。

`back_populates` 把两边声明成 **同一条关系的两端**。如果漏掉，SQLAlchemy 会当成两套单向关系，同步和级联都会乱。

本阶段没有 `Tenant.users` 的 association_proxy，避免一层魔法。需要用户信息时走 `member.user`。

## 创建租户的事务

Service 里顺序是：

1. `session.add(tenant)`
2. `session.flush()` 拿到 `tenant.id`（还没提交）
3. `session.add(member)`，role=OWNER
4. `session.commit()`

任何一步抛错都 `rollback()`。这样不会出现「企业建成了但没有创建者」的半成品。Repository 禁止 `commit`。

## TenantContext 如何注入

`X-Tenant-ID` 只是「我想访问哪家企业」。FastAPI 依赖链：

1. `get_current_user`：解析 Access Token
2. `get_tenant_context`：读请求头 → 查 `tenant_members` → 校验成员和租户状态
3. 业务函数参数写成 `context: TenantContextDep`

不要把 `tenant_id` 写进 JWT。切换企业只改请求头，不必重新 RSA 登录。

创建租户、我的租户列表、登录注册 **不要求** 这个头。后续 `products` 这类业务接口必须要求。

## 为什么不能信任 X-Tenant-ID

请求头和 JSON 体都可以伪造。攻击者登录后把 `X-Tenant-ID` 改成别人的企业 ID，如果服务端不查成员表，就会读到别人的库存。

所以服务端必须用 **JWT 里的 user_id + 请求头里的 tenant_id** 去查 `tenant_members`。没有行、成员禁用、企业禁用，都不能进入租户上下文。

对「根本不是成员」的企业，统一返回 404「租户不存在或不可访问」，避免用不同文案证明某家企业存在。

## 为什么 Repository 必须带 tenant_id

`GET /products/1` 如果只按主键查，ID 在全局自增时可能落到别的企业。正确写法：

```python
select(Product).where(Product.id == product_id, Product.tenant_id == context.tenant_id)
```

`tenant_id` 必须来自已校验的 `TenantContext`，不能直接用前端又传一遍的值当「已授权」。

`TenantMixin` 给未来业务表提供这一列和指向 `tenants.id` 的外键。不要做隐式全局过滤器，查询条件写在 Repository 里，方便测试和排错。

## 联合唯一约束和联合索引

- **联合唯一约束** `UNIQUE(tenant_id, user_id)`：数据库拒绝重复行。这是业务规则。
- **联合索引** `INDEX(tenant_id, sku_code)`：只加速查找，允许重复，除非同时声明 UNIQUE。

InnoDB 的 UNIQUE 本身会建索引，所以唯一约束已经能加速 `(tenant_id, user_id)` 查询。如果还要按 `user_id` 单独列「我加入了哪些企业」，外键 `user_id → users.id` 会再带一个单列索引。

未来库存表常用：

```sql
UNIQUE (tenant_id, sku_code)
UNIQUE (tenant_id, warehouse_id, sku_id)
```

漏掉 `tenant_id` 会让不同企业的 SKU 编码互相冲突。

## Redis

租户缓存：`erp:tenant:{tenant_id}:product:{id}`

认证会话仍用全局键：`auth:refresh:{jti}`、`auth:challenge:{id}`。Refresh Token 属于用户，不属于当前企业。

## 最小权限（V2.3 会被 RBAC 替换）

- 创建者：`tenant_members.role = OWNER`，可添加/禁用本企业成员
- 普通成员：可看本企业信息和成员列表，不能改别人
- 完整角色权限表本阶段不建
