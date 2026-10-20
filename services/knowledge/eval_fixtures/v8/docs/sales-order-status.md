# 销售订单状态

来源：`services/erp/app/models/sales_order.py` 的 `SalesOrderStatus`。本文只转写代码注释中的状态含义，不是新的业务规则。

## 状态

| 状态 | 代码注释中的含义 |
| --- | --- |
| DRAFT | 草稿。可改客户、仓库、收货信息和明细；可提交或取消。未预占库存。 |
| PENDING_CONFIRMATION | 待确认。已提交、等待审核。确认才会预占库存；也可取消且不动库存。 |
| WAITING_OUTBOUND | 待出库。已确认并预占。尚未正式出库时可以整单取消并释放预占。 |
| PARTIALLY_OUTBOUND | 部分出库。已经扣过库存，不能整单取消。 |
| OUTBOUNDED | 已出库。购买数量都已离开库存账面，尚未全部交给承运商。 |
| PARTIALLY_SHIPPED | 部分发货。已经有物流单确认发货。 |
| SHIPPED | 已发货。订单数量都已交给承运商。 |
| COMPLETED | 已完成。全部物流单都已签收。 |

状态只能经提交、确认、取消流转，不要直接改 status 列。
