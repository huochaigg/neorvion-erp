# 出库超过预占

来源：`services/erp/app/services/outbound.py`。

出库数量超过已预占数量时，接口数据里的 error 为 `OUTBOUND_EXCEEDS_RESERVED`。

该错误码不是 `INSUFFICIENT_RESERVED_INVENTORY`。后者出现在释放预占超过 reserved_quantity 的库存路径。
