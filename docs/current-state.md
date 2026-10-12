# 当前状态

**Neorvion ERP Core V1**（V15 收口）。只记录当前有效架构。版本历史见 `docs/versions/`。

## 技术栈

Shell（8015）+ ERP 微前端（8016）+ FastAPI（8011）+ MySQL 8 + Redis 7 + 独立 Worker。前端 React 19 / Vite / Wujie / Ant Design 6 / TanStack Query / Zustand。后端 SQLAlchemy 2 / Alembic。

## 目录

- `apps/shell`：登录、租户、导航、Wujie 宿主
- `apps/erp`：业务页面
- `packages/shared`：Query Key、ApiError、租户请求头
- `backend/app/{api,core,models,schemas,repositories,services,tasks}`
- `docs/`：导航见 `docs/README.md`

## 核心模块

Catalog、Warehouse、Inventory、Purchase、Sales、Fulfillment（收货 / 出库）、Shipping、Stocktake、Transfer、After-Sales、Purchase Return、Analytics、Events、Operation Logs、Async Tasks。SaaS 多租户 + RBAC。

## 库存

| 字段 | 是否落库 | 含义 |
| --- | --- | --- |
| `quantity` | 是 | 仓库实数，必须 `>= 0` |
| `reserved_quantity` | 是 | 已预占未出库，`>= 0` 且 `<= quantity` |
| `available_quantity` | 否 | `quantity - reserved_quantity` |

确认订单：只增加 reserved。确认出库：quantity 与 reserved 同减。采购入库 / 退货入库：只加 quantity。采购退货出库 / 调拨调出：只减 available（quantity），不偷释放销售预占。

## 销售订单

草稿 → 提交 → 确认（预占）→ 部分/全部出库 → 部分/全部发货 → 签收完成。取消释放预占。`SHIPPED` 只表示物流，出库状态用 `OUTBOUNDED`。售后不改原 `SalesOrderItem.quantity`，也不把已完成订单改回履约中。

销售明细：`reserved_quantity + outbound_quantity <= quantity`；`shipped_quantity <= outbound_quantity`。

## 采购

草稿 → 提交 → 审核（不改库存）→ 收货入库。可部分收货。`PurchaseOrderItem.received_quantity <= quantity`。采购退货占用已收数量，不改原计划数 / 已收数。

## 售后

可退 = 已出库 − 有效售后占用。退款累计不超过已批准可退金额。`RefundRecord` 是人工确认结果，不接支付渠道。

## 事件 / 任务 / 日志

- `system_events`：业务事实 + Outbox，与主事务同写
- `operation_logs`：谁做了什么；脱敏，不含 Authorization / token
- `async_tasks`：状态在 MySQL；Redis List 只投递 `task_id`
- Worker：`uv run python -m app.tasks.worker`，心跳 `erp:worker:heartbeat`

## Analytics

实时 MySQL 聚合。无汇总表、无 ClickHouse、无 Redis 库存缓存。CSV 导出会处理 Formula Injection。

## 认证 / 租户 / RBAC

RSA-OAEP 传密码；Refresh Cookie HttpOnly；Access Token 给 JS。跨租户 404。Permission 全局，Role 租户内。系统角色 OWNER / ADMIN / OPERATOR / WAREHOUSE / VIEWER。

## 事务规则

Repository 不 commit。Service 管事务。多 SKU 升序加锁。库存条件 UPDATE + 必要行锁。

## 时间

数据库 DateTime 为 naive 墙钟时间（开发按本地理解）。前端展示 `YYYY-MM-DD` / `YYYY-MM-DD HH:mm:ss`。未全面 timezone-aware。

## Agent 可复用只读 API

商品 / 库存 / 销售订单 / 采购单 / 售后 / Analytics / Event / Task 查询。写操作必须走 ERP API + RBAC + 状态机。Agent 不直连 MySQL。

## 已知限制

无真实支付 / 承运商 API / 库位批次 / 次品台账 / Kafka / OpenTelemetry / 通知中心 / OLAP。金额 API Out 部分为 float 展示，库内 Numeric/Decimal。全文搜索未做，列表 `LIKE %keyword%` 仅适合当前数据量。演示数据是 synthetic。
