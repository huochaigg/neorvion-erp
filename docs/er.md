# 核心 ER（示意）

不是全库 45+ 张表。只帮助建立心智模型。

## IAM 身份 / RBAC（`neorvion_iam`）

ERP 不再持有这些表。跨服务只引用整数 ID。

```mermaid
erDiagram
  users ||--o{ tenant_members : joins
  tenants ||--o{ tenant_members : has
  tenants ||--o{ roles : has
  tenant_members ||--o{ member_roles : has
  roles ||--o{ member_roles : grants
  roles ||--o{ role_permissions : has
  permissions ||--o{ role_permissions : catalog
  users ||--o{ auth_sessions : sessions
```

## ERP 展示名快照（`neorvion_erp`）

```mermaid
erDiagram
  identity_name_snapshots {
    bigint user_id PK
    varchar display_name
  }
  sales_orders }o--|| identity_name_snapshots : created_by
```

`sales_orders.created_by` 等列**没有**外键，JOIN 快照只为展示。

## 商品 / 库存

```mermaid
erDiagram
  products ||--o{ product_skus : contains
  warehouses ||--o{ inventories : holds
  product_skus ||--o{ inventories : stocked
  inventories ||--o{ inventory_transactions : ledger
```

## 采购 / 销售 / 履约

```mermaid
erDiagram
  purchase_orders ||--o{ purchase_order_items : lines
  purchase_orders ||--o{ purchase_receipts : receives
  sales_orders ||--o{ sales_order_items : lines
  sales_orders ||--o{ outbound_orders : fulfills
  outbound_orders ||--o{ shipments : ships
```

## 售后 / 事件

```mermaid
erDiagram
  sales_orders ||--o{ after_sale_orders : reverse
  after_sale_orders ||--o{ return_orders : returns
  after_sale_orders ||--o{ refund_records : refunds
```

`system_events` / `async_tasks` 带 `tenant_id` 整数，不指向 IAM `tenants` 表。

```mermaid
erDiagram
  system_events {
    bigint tenant_id
  }
  async_tasks {
    bigint tenant_id
  }
```
