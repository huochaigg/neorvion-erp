# 业务异常与状态边界（已实现）

来源：销售、库存、盘点测试中的错误码。以下异常会真实返回，不是文档设想。

## 库存

- `INSUFFICIENT_RESERVED_INVENTORY`：释放或出库的预占数量超过 `reserved_quantity`。
- `STOCKTAKE_CONFLICT_WITH_RESERVED_INVENTORY`：盘点调整与预占冲突。
- 可用库存不足时不能确认订单完成预占。

## 订单

- 非 CANCELLABLE 状态整单取消会被拒绝。PARTIALLY_OUTBOUND 之后不能整单取消。
- 不能跳过确认直接出库：必须先到 WAITING_OUTBOUND。
- 草稿未提交时确认无效。

## 租户与权限

- 无 `knowledge:read` 时 Knowledge API 返回 403。
- 访问其他租户资源返回 404 或 403，不泄露是否存在。

## 模拟案例（非生产数据）

【模拟案例】租户 3 将 SKU A 确认 2 件：`quantity` 仍为 10，`reserved_quantity` 变为 2，可用 8。随后出库 2 件：`quantity` 变为 8，`reserved_quantity` 变为 0。
