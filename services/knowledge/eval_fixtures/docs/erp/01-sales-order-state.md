# 销售订单状态机（已实现）

来源：`services/erp/app/models/sales_order.py`、`services/erp/app/services/sales_order.py`、`services/erp/app/services/sales_order_state.py`。以下描述当前代码行为，不是建议中的理想流程。

## 草稿 DRAFT 与库存预占

`DRAFT` 是可编辑的草稿态。此时可以修改客户、仓库、收货信息和订单明细，也可以提交或整单取消。

**DRAFT 不会预占库存。** 草稿里的购买数量只是计划，不会增加 `reserved_quantity`，也不会减少 `quantity`。把草稿理解成“已经锁库存”是错误的。

只有草稿属于可编辑集合 `EDITABLE_STATUSES`。提交后不能再改核心字段。

## 提交：DRAFT → PENDING_CONFIRMATION

`submit_order` 把草稿提交为待确认。提交只表示资料齐了，等待拥有 `order:audit` 的人确认。**提交仍然不预占库存。** 确认时仓库可用量可能已经变化，所以提交通过不代表确认一定成功。

待确认阶段取消订单也不会动库存：确认前没有 RESERVE，取消只需改状态。

## 确认：PENDING_CONFIRMATION → WAITING_OUTBOUND

`confirm_order` 只能从 `PENDING_CONFIRMATION` 进入 `WAITING_OUTBOUND`。确认时调用 `InventoryService.reserve_within_transaction`，库存流水类型为 `RESERVE`，引用类型为 `SALES_ORDER`。

确认只增加 `reserved_quantity`，**不扣减 `quantity`**。货还在仓库里，只是被这张订单占住。明细 `reserved_quantity` 写成购买数量。可用库存因此下降：可用 = `quantity - reserved_quantity`。

草稿直接确认无效。必须先提交到待确认。

## 取消与库存释放

可取消集合 `CANCELLABLE_STATUSES`：`DRAFT`、`PENDING_CONFIRMATION`、`WAITING_OUTBOUND`。

- 草稿、待确认取消：不写库存流水。
- 待出库整单取消：同一事务调用 RELEASE，减少 `reserved_quantity`，明细预占归零。
- `PARTIALLY_OUTBOUND` 已经扣过库存，不能整单取消。

## 出库后的订单状态

履约状态由明细数量计算，不由前端 PATCH status：

- `PARTIALLY_OUTBOUND`：已有正式出库，不能整单取消。
- `OUTBOUNDED`：购买数量都已离开库存账面，**尚未全部交给承运商**。
- `PARTIALLY_SHIPPED` / `SHIPPED`：部分或全部交给承运商。
- `COMPLETED`：全部物流单都已签收。

拣货本身不改变这些销售订单状态，也不扣库存；确认出库才扣减。详见出库文档。

## 合法流转（已实现）

- `DRAFT` → `PENDING_CONFIRMATION` 或 `CANCELLED`
- `PENDING_CONFIRMATION` → `WAITING_OUTBOUND` 或 `CANCELLED`
- `WAITING_OUTBOUND` → `PARTIALLY_OUTBOUND`、`OUTBOUNDED` 或 `CANCELLED`
- `PARTIALLY_OUTBOUND` → `OUTBOUNDED`、`PARTIALLY_SHIPPED` 或 `SHIPPED`
- `OUTBOUNDED` → `PARTIALLY_SHIPPED` 或 `SHIPPED`
- `PARTIALLY_SHIPPED` → `SHIPPED` 或 `COMPLETED`
- `SHIPPED` → `COMPLETED`
- `COMPLETED` / `CANCELLED` 无出口

可出库集合：`WAITING_OUTBOUND`、`PARTIALLY_OUTBOUND`、`PARTIALLY_SHIPPED`。
