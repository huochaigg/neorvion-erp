# IAM、多租户与功能 RBAC

身份、租户、功能 RBAC 以 IAM 为权威来源。ERP 与 Knowledge 普通接口消费 Redis 授权快照；高风险接口回源 IAM。资源级 ACL 仍在各业务服务。内部 SSO 不是 OIDC。

## 四层不要混为一谈

1. Authentication：你是不是这个用户？密码、JWT、Refresh Cookie。
2. Tenant Membership：现在代表哪家企业？`tenant_members` + `X-Tenant-ID` + Redis 快照。
3. RBAC：允不允许这个操作？角色上的权限码，例如 `knowledge:read`。
4. ACL：允不允许动这一本知识库？Knowledge 的 `KnowledgeBaseGrant`。

「JWT 验过了所以有权限」「Header 里写了租户所以安全」都不是当前实现。

## User、成员、角色、权限

```text
User（全局人）
  └── TenantMember（这个人在这家企业的身份）
        └── MemberRoleGrant
              └── Role（这家企业自己的角色）
                    └── RolePermission
                          └── Permission（平台统一权限目录）
```

`User` 有邮箱、密码和全局显示名，没有 `tenant_id`。一个人可以加入多家企业。`TenantMember.role` 仍表示所有权（`OWNER` / `MEMBER`），不是细粒度权限。`Role` 属于具体租户：Acme 的 `ADMIN` 和 Beta 的 `ADMIN` 是两行。`Permission` 是平台统一定义的操作编码。`RolePermission` 才表示某个租户角色实际拥有哪些目录项。

最终权限 = 当前租户下该成员所有有效角色权限的并集。OWNER 列另外表示所有权：目录里已登记的权限，所有者全部拥有。

不要把角色写进 `users` 表。不要用全局用户角色代替租户角色。企业管理员不能通过成员接口改邮箱、密码或 User 全局名称。

`UNIQUE(tenant_id, code)`：同一企业角色编码不重复；不同企业可以都叫 `ADMIN`。查询、更新、删除角色时必须带已校验的 `TenantContext.tenant_id`。只凭 URL 里的 `role_id` 会越权读到别的企业。

`member_roles` 用复合外键同时指向 `(tenant_id, member_id)` 和 `(tenant_id, role_id)`。即使应用层写错，数据库也会拒绝把租户 A 的成员挂到租户 B 的角色。

## 权限目录是全局的

`tenant:member:create`、`order:audit`、`knowledge:read` 对所有企业含义相同。租户不能 CRUD 权限目录。用户自行创建的 code 若从未被 `require_permission` 使用，则没有任何实际意义。未知 code 是服务端配置错误（`50021`），不能悄悄放行。

`PermissionCode` 表示代码真实支持的能力，不是某个角色的固定清单。角色授权界面是 DIRECTORY → MENU → ACTION 树。树只是 UI；真正授权仍写入 `role_permissions`。React 路由由各应用 `routes.ts` 驱动，不能由租户在数据库里随便新增前端页面。

部分历史粗粒度码保留兼容，例如 `tenant:member:manage`、`tenant:role:manage`，不再用于新接口校验。

## Knowledge 功能权限

IAM 与 Knowledge 服务都声明了同一组编码：

| 编码 | 含义 |
| --- | --- |
| `knowledge:read` | 查看当前企业知识库列表与详情、检索、问答、读评测 |
| `knowledge:create` | 创建知识库、启动评测运行等写入口 |
| `knowledge:update` | 修改知识库、重建索引、模型连通测试 |
| `knowledge:delete` | 删除知识库；高风险，回源 IAM |

这是 IAM 权限枚举中的字符串，不是 ERP 销售订单状态，也不是 `order:read`。Knowledge 删除属于高风险权限集合。

## `X-Tenant-ID` 只是意愿

前端传入的 `X-Tenant-ID` 必须与 JWT / Redis 快照中的成员关系交叉验证。产品代码不能只信这个请求头。Knowledge API 在 `AuthorizationService.require_all` 之后还要核对租户成员。测试与脚本若模拟租户上下文，必须带齐 `user_id`、`tenant_id` 与权限集合。

ERP 与 Knowledge 的业务表带 `tenant_id`。复合外键始终带租户，避免把 A 企业的仓库挂到 B 企业的订单。跨库没有外键，隔离靠每个服务自己的查询条件。禁止先全局召回再在 Python 里丢弃其他租户。

## JWT、快照与撤销

Access Token 为 RS256，响应体 `access_token`。Refresh Token 走 HttpOnly Cookie 与 Redis GETDEL，`auth_sessions` 存 jti 哈希，明文 Refresh 不入库。密码传输使用与 JWT 分离的 RSA-OAEP；口令哈希为 Argon2id。

Knowledge 本地校验 IAM RS256 JWT，读 Redis 授权快照。普通读接口崩溃窗口仍可达快照 TTL，不是跨库两阶段提交，不是强一致。撤权后短期窗口内旧 Access 仍可能让普通读成功。

高风险操作（删除仓库、删除知识库、确认退款等）调用 IAM `internal/authorize`，以数据库为准，不用过期快照放行。生产必须配置 `IAM_AUTHORIZE_URL`。

登录失败不区分邮箱是否存在。内部多微前端共享同一 Access 与 Cookie，这不是 OIDC，不能对接企业 IdP。

## 默认角色模板不是安全边界

OWNER / ADMIN 默认拥有已登记的全部功能权限。OPERATOR、WAREHOUSE、VIEWER 的默认集合随版本补齐，例如 VIEWER 可 `event:read`，不可 `operation_log:read`。按钮组件无权限则隐藏或禁用，那不是安全边界；真正拒绝发生在 API 的 `require_permission`。

菜单表未驱动 ERP 运行时菜单。Shell 顶栏不按权限藏入口。面试或文档若把「菜单自动按权限消失」说成已实现，与源码不符。

## 资源 ACL 与租户隔离同时存在

Knowledge 知识库另有 grants：非所有者即使有 `knowledge:read`，也不一定能读某一本库。ERP 订单主要靠租户隔离和归属字段，不是独立 ACL 引擎，本版无 ABAC。

会话可列出、撤销、全退。JWT 带 `sid`。撤销会话后，Access 短期窗口内普通读接口仍可能成功，直到过期。

## 业务权限码分组

下列编码来自 `services/iam/app/core/permissions.py` 的 `PermissionCode`，不是某租户私有目录。

| 领域 | 编码前缀 | 例子 |
| --- | --- | --- |
| 租户与成员 | `tenant:` | `tenant:member:create`、`tenant:role:permission:update` |
| 商品 | `product:` | `product:read` / `create` / `update` / `delete` |
| 销售订单 | `order:` | `order:submit`、`order:audit`、`order:cancel` |
| 客户 | `customer:` | `customer:disable` |
| 库存 | `inventory:` | `inventory:initialize`、`inventory:adjust` |
| 仓库 | `warehouse:` | `warehouse:disable` |
| 采购与收货 | `purchase:` | `purchase:audit`、`purchase:receipt:confirm` |
| 出库 | `outbound:` | `outbound:pick`、`outbound:confirm` |
| 物流 | `shipment:` / `carrier:` | `shipment:deliver` |
| 盘点 / 调拨 | `stocktake:` / `stock_transfer:` | `stock_transfer:outbound` |
| 售后 | `after_sale:` / `return_order:` / `refund:` | `refund:confirm` |
| 采购退货 | `purchase_return:` / `supplier_refund:` | `purchase_return:outbound` |
| 分析 | `analytics:` | `analytics:inventory:read` |
| 知识库 | `knowledge:` | `knowledge:read` |

`order:audit` 是销售确认。`purchase:audit` 是采购批准。两者都叫审核，库存效果不同。`outbound:confirm` 才是销售出库扣库存。

## 快照版本

IAM 在授权变更时更新 `authz_revisions`，Redis 键与账号版本、租户版本相关（文档中的 `iam:aver` / `iam:tver` 一类加速键）。ERP 与 Knowledge 读快照加速普通接口。高风险接口忽略过期快照，回源 IAM 库。没有跨库 2PC，撤权不是全局瞬时强一致。

Knowledge 校验 JWT 的 issuer、audience、算法。`alg=none` 与错误 issuer 必须拒绝。业务进程可缓存 JWKS，缓存过期后重新拉取。

## 高风险权限集合分服务

Knowledge 服务 `HIGH_RISK_PERMISSION_CODES` 目前是 `{knowledge:delete}`。删除知识库走 IAM `internal/authorize`，不用过期 Redis 快照放行。

ERP 服务的高风险集合是另一份名单，包括 `warehouse:delete`、`product:delete`、`customer:delete`、`refund:confirm`、`supplier_refund:confirm`、`purchase_return:approve`。不要把 Knowledge 的删除码写进 ERP 集合，也不要把 ERP 的退款确认写进 Knowledge 集合。

两边都通过 `high_risk_verified` 判断本次请求是否已经回源。普通 `knowledge:read` 检索、问答、读评测仍走快照。

## Redis 键不要改租户语义

| 键 | 是否带租户 | 含义 |
| --- | --- | --- |
| `iam:snap:{user}:{tenant}` | 是 | 授权快照 |
| `iam:aver:{user}:{tenant}` | 是 | 授权版本 |
| `iam:tver:{user}` | 否 | 令牌版本，失效的是这个人的登录 |
| `iam:refresh:{jti}` | 否 | Refresh 一次性读取 |
| `iam:csrf:{jti}` | 否 | CSRF |

`iam:tver` 和 Refresh 不带租户：注销的是这个人，不是某一家企业。授权失效用 `iam:aver`。变更在同一 MySQL 事务内递增 `authz_revisions` 并写 outbox；Pub/Sub 不是正确性保证。

OWNER 拥有目录里已登记的全部功能权限。按钮隐藏不是安全边界。未知权限码是服务端配置错误 `50021`，不能悄悄放行。

## 成员接口不能改全局 User

企业管理员给成员授角色、停用成员、调整 `OWNER` / `MEMBER` 所有权标记，都不能通过成员接口改邮箱、密码或 User 全局显示名。密码与 JWT 使用分离的 RSA-OAEP 传输，口令哈希 Argon2id。

登录失败不区分邮箱是否存在。内部多微前端共享同一 Access 与 Cookie，这不是 OIDC，不能对接企业 IdP。Refresh Token 走 HttpOnly Cookie 与 Redis GETDEL；`auth_sessions` 存 jti 哈希，明文 Refresh 不入库。

Knowledge 与 ERP 都在 `require_all` 之后核对租户成员。脚本模拟上下文必须带齐 `user_id`、`tenant_id` 与权限集合，不能只设 `X-Tenant-ID`。

生产必须配置 `IAM_AUTHORIZE_URL`。高风险校验失败应拒绝，不能回退成只信快照。JWT audience 必须包含本服务：Knowledge 为 `neorvion-knowledge`，ERP 为 `neorvion-erp`。错误 audience 或 `alg=none` 必须拒绝。

