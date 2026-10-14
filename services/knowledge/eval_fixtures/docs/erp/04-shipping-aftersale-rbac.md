# 物流、售后、多租户与 RBAC（已实现）

来源：物流发货、售后、退款、`docs/rbac.md`、`docs/multi-tenancy.md`。身份权威在 ERP MySQL。Knowledge 不另建用户表。

## 物流与签收

出库完成后才能创建物流单。部分交给承运商对应销售订单 `PARTIALLY_SHIPPED`，全部交给承运商后为 `SHIPPED`。`OUTBOUNDED` 只表示购买数量已离开库存账面，不等于已经交给承运商。

全部物流单都已签收后，订单进入 `COMPLETED`。COMPLETED 必须由签收结果决定，不能由前端直接改状态。

## 售后、退款与退货

售后来自已履约订单。类型包括 `REFUND_ONLY`（仅退款）、`RETURN_AND_REFUND`（退货退款）、`RETURN_ONLY`（仅退货）。

退货入库写库存流水 `RETURN_INBOUND`。**退款与退货状态独立**：`RefundStatus.SUCCESS` 不代表库存已经加回。不能把退款成功理解成 `RETURN_INBOUND` 已经发生。仅退款不要求退回商品，不会写退货入库。

## 多租户

所有业务查询必须带服务端 `tenant_id`。前端 `X-Tenant-Id` 只是意愿，必须经成员关系校验。禁止客户端指定其他企业 ID 读取订单或库存。Token 属于 A 企业时配上 B 的 Header，不能单靠 Header 读 B 的库存。

访问其他租户资源返回 404 或 403，**不泄露资源是否存在**。

## RBAC

权限编码绑定角色，角色绑定成员。Knowledge 复用 ERP 权限码 `knowledge:read/create/update/delete`，无 `knowledge:read` 时 Knowledge API 返回 403。企业所有者可管理成员；普通成员只拥有角色授予的权限。
