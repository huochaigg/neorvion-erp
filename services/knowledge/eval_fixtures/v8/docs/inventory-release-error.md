# 释放预占与盘点冲突

来源：`services/erp/app/services/inventory.py` 与 `services/erp/tests/test_inventory.py`。

释放预占超过 reserved_quantity 时，错误码是 `INSUFFICIENT_RESERVED_INVENTORY`。

盘点调整和预占冲突时，错误码是 `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`。测试 `test_stocktake.py` 也断言该错误码。

这两个错误码不能互换，也不能写成出库超额的 `OUTBOUND_EXCEEDS_RESERVED`。
