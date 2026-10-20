# 采购收货确认

来源：`services/erp/app/services/purchase_receipt.py` 模块说明。

草稿收货单不入库。确认收货才增加 quantity，并且和采购进度同一事务。

确认时只加 quantity，不改 reserved。确认逻辑不自己 commit。

这与销售订单确认不同：销售确认写的是预占，采购收货确认增加的是 quantity。
