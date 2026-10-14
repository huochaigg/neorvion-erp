# 业务异常与状态边界（已实现）

来源：销售、库存、出库、盘点服务中的错误码。以下异常会真实返回，不是文档设想。

## 库存

- `INSUFFICIENT_RESERVED_INVENTORY`：释放或出库的预占数量超过 `reserved_quantity`。
- `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`：盘点调整与预占冲突。
- 可用库存不足时不能确认订单完成预占。

## 订单

- 非 CANCELLABLE 状态整单取消会被拒绝。`PARTIALLY_OUTBOUND` 之后不能整单取消。
- **不能从草稿直接出库**：必须先提交、确认，进入 `WAITING_OUTBOUND`。草稿未提交时确认无效。
- 非法流转返回 `INVALID_SALES_ORDER_TRANSITION`。

## 出库

- 只有待拣货出库单可以拣货。已拣货、已出库、已取消都不能再拣。
- 确认出库前必须先确认拣货：状态不是 `PICKED` 时返回“请先确认拣货，再确认出库”。
- 出库单已经确认则不能重复扣减库存。

## 租户与权限

- 无 `knowledge:read` 时 Knowledge API 返回 403。
- 访问其他租户资源返回 404 或 403，不泄露是否存在。

## 模拟案例（非生产数据）

【模拟案例】租户 3 将 SKU A 确认 2 件：原 `quantity=10` 时，`quantity` 仍为 10，`reserved_quantity` 变为 2，可用 8。随后出库 2 件：`quantity` 变为 8，`reserved_quantity` 变为 0。该段标明为模拟案例，不是某张真实单据。
