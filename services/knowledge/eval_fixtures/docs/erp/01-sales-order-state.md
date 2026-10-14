# 销售订单状态机（已实现）

来源：`services/erp/app/models/sales_order.py`、`services/erp/app/services/sales_order.py`、`services/erp/app/services/sales_order_state.py`。以下描述当前代码行为，不是建议中的理想流程。

## 状态列表

| 状态 | 含义 |
| --- | --- |
| DRAFT | 草稿。可改客户、仓库、收货信息和明细；可提交或取消。未预占库存。 |
| PENDING_CONFIRMATION | 待确认。已提交、等待审核。确认才会预占库存；也可取消且不动库存。 |
| WAITING_OUTBOUND | 待出库。已确认并预占。尚未正式出库时可以整单取消并释放预占。 |
| PARTIALLY_OUTBOUND | 部分出库。已经扣过库存，不能整单取消。 |
| OUTBOUNDED | 已出库。购买数量都已离开库存账面，尚未全部交给承运商。 |
| PARTIALLY_SHIPPED | 部分发货。已经有物流单确认发货。 |
| SHIPPED | 已发货。订单数量都已交给承运商。 |
| COMPLETED | 已完成。全部物流单都已签收。 |
| CANCELLED | 已取消。 |

## 合法流转（已实现）

- PENDING_CONFIRMATION → WAITING_OUTBOUND 或 CANCELLED
- WAITING_OUTBOUND → PARTIALLY_OUTBOUND、OUTBOUNDED 或 CANCELLED
- 可取消集合：DRAFT、PENDING_CONFIRMATION、WAITING_OUTBOUND
- 可出库集合：WAITING_OUTBOUND、PARTIALLY_OUTBOUND、PARTIALLY_SHIPPED

确认订单时调用库存 RESERVE，不扣减 `quantity`。出库时才同时扣减 `quantity` 与 `reserved_quantity`。

WAITING_OUTBOUND 整单取消会 RELEASE 预占。一旦进入 PARTIALLY_OUTBOUND，不能整单取消。

库存流水的销售订单引用类型为 `SALES_ORDER`。
