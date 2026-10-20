# 采购单状态

来源：`services/erp/app/models/purchase.py` 的 `PurchaseOrderStatus`。

审核通过不改库存；收货确认才增加 quantity。

| 状态 | 代码注释中的含义 |
| --- | --- |
| DRAFT | 草稿。可改供应商、仓库和明细；可提交审核或取消。未入库。 |
| PENDING_APPROVAL | 待审核。可批准进入待收货、驳回，或取消。批准同事务直达待收货，无单独 APPROVED。 |
| WAITING_RECEIPT | 待收货。审核已通过，等待收货入库。可部分收货或一次收完；本版本不可取消。 |
| PARTIALLY_RECEIVED | 部分收货。已有收货单入库，但仍有未收完的明细。 |
| RECEIVED | 已收货。全部明细收齐。终态，不能再流转。 |
| REJECTED | 已驳回。可改单后重新提交，或取消。 |
| CANCELLED | 已取消。终态，不能再流转。 |

采购单批准和销售订单确认不是同一件事：采购批准不增加库存。
