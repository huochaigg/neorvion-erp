# 性能与索引

V15 不为作品集做复杂压测，也不提前分库、ClickHouse、ES、读写分离。

## 预算

- 普通 CRUD：开发环境正常响应
- 列表：`page_size <= 100`
- Analytics：典型 30 天聚合可接受
- 不声称百万 QPS 或生产容量

当前开发数据量是几百 / 几千行。查询正常时不要为 WHERE 再堆索引。

## 已有索引方向

业务列表普遍 `tenant_id + created_at` / `tenant_id + status + created_at`。库存 `(tenant_id, warehouse_id, sku_id)` 唯一。事件 `aggregate_type + aggregate_id`、`occurred_at`。任务 `tenant_id + status + created_at`。

## LIKE 搜索

`keyword` / 名称 / SKU / 单号当前允许 `LIKE '%xxx%'`。数据量上来后需要前缀索引或全文检索。V15 不引入 Elasticsearch。

## N+1

详情使用 `selectinload` 加载一对多（订单明细、SKU）。分页列表避免 JOIN 多集合造成重复行。报表 Top N 用 SQL 聚合，不在 Python 循环查 relationship。

## EXPLAIN 摘要

在开发库（数据量为测试/演示级，**不是生产容量证明**）对代表性查询执行 `EXPLAIN`：

| 查询 | type | key | Extra |
| --- | --- | --- | --- |
| 销售订单列表 tenant + created_at DESC | ref | `ix_sales_orders_tenant_created` | Backward index scan |
| 库存列表 tenant | ref | `uq_inventories_tenant_id` | Backward index scan |
| 采购列表 tenant + created_at DESC | ref | `ix_purchase_orders_tenant_created` | Backward index scan |
| 售后列表 tenant + created_at DESC | ref | `ix_after_sale_orders_tenant_created` | Backward index scan |
| 销售 30 天按日 COUNT | ref | `uq_sales_orders_tenant_id` | Using where; Using temporary |
| 事件列表 tenant + occurred_at DESC | ref | `ix_system_events_tenant_occurred` | Backward index scan |
| 任务列表 tenant + created_at DESC | ref | `ix_async_tasks_tenant_created` | Backward index scan |

没有业务全表 `type=ALL`。趋势聚合的 `Using temporary` 在当前数据量可接受；数据量上来后再考虑按日汇总表，不在 V15 引入。

连接池见 `docs/architecture.md`：2C2G 上 `pool_size=5` + `max_overflow=5`。
