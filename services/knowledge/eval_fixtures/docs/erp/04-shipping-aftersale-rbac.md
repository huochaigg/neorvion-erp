# 物流、售后、多租户与 RBAC（已实现）

来源：物流发货、售后、退款、`docs/rbac.md`、`docs/multi-tenancy.md`。身份权威在 ERP MySQL。

## 物流

出库完成后才能创建物流单。部分发货对应 PARTIALLY_SHIPPED，全部交给承运商后为 SHIPPED。全部签收后订单 COMPLETED。

## 售后

售后来自已履约订单。退货入库写 RETURN_INBOUND。退款与退货状态独立，不能把退款成功理解成库存已加回。

## 多租户

所有业务查询必须带服务端 `tenant_id`。前端 `X-Tenant-Id` 只是意愿，必须经成员关系校验。禁止客户端指定其他企业 ID 读取订单或库存。

## RBAC

权限编码绑定角色，角色绑定成员。Knowledge 复用 `knowledge:read/create/update/delete`，不另建用户表。企业所有者可管理成员；普通成员只拥有角色授予的权限。
