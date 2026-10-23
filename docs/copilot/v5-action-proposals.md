# ERP Copilot V5：Action Proposal

## 安全边界

V5 只生成 Copilot 自有草稿并请求 ERP 无副作用预检。Action Registry 没有 Execute Handler；
Copilot ERP Client 只允许三个固定 `action-previews` 路径，模型不能提供 URL、Token、tenant_id 或 user_id。
ERP 仍以原始用户 JWT、已验证租户和真实 create 权限独立鉴权。`READY` 不是 ERP 单据状态，也不是执行授权。

## 状态与并发

`DRAFT` 表示字段齐全但尚未通过预检；`NEEDS_INPUT` 表示缺少必要字段；`READY` 表示当前 revision
在未过期时预检通过；编辑或预检过期展示 `STALE`；取消和提案过期分别为 `CANCELLED`、`EXPIRED`。
PATCH、validate、cancel 都携带 `expected_revision`，不一致返回 409。编辑创建新 revision，旧 validation 不会
用于新 revision。创建幂等范围是 tenant + user + idempotency_key；同键不同内容返回 409。

## ERP Preview 契约

三个 Preview 直接接收 ERP 现有 `PurchaseOrderCreate`、`SalesOrderCreate`、`StockTransferCreate` Schema。
Service 复用真实实体/状态/SKU 校验，并返回：

- `valid`、`blocking_errors`、`warnings`、`missing_fields`
- `normalized_payload`、`preview_summary`
- `resource_versions`、`validated_at`、`expires_at`

Preview 不调用正式创建 Service，不写订单或明细，不预占/扣减库存，不生成事件、操作流水或任务。
销售草稿创建本身允许无价格和库存不足，因此 Preview 按真实创建语义给 warning；调拨 Preview 按 V5
安全要求把源仓库存不足列为 blocking error。

## 部署与回滚

在 Copilot 独立数据库执行 `alembic upgrade head`，目标 revision 为 `20261023_0003`。上线前备份
`neorvion_copilot`，在可销毁测试库验证 downgrade 到 `20261023_0002` 后再 upgrade。回滚应用版本前，
先停止 V5 写流量；代码回滚但保留新表是首选。只有确认不再需要 V5 草稿且已有备份时，才在维护窗口
执行 downgrade。旧 `neorvion_knowledge` 中遗留的 Copilot 表不属于本迁移，未经授权不得删除。

## 验收检查

1. 迁移升级后创建三类 Proposal，验证 tenant/user/conversation 外键和 revision 唯一约束。
2. 对每个 Preview 前后比对正式订单、明细、库存三量、事件、操作日志和任务行数。
3. 并发 PATCH 同一 revision，确认仅一个成功，另一个返回 409。
4. 断开 SSE 后通过 Proposal API 恢复已提交草稿。
5. 切换租户、撤销动作权限，确认列表与详情均不泄露原租户/无权草稿。
6. 真实模型尝试“直接执行”，确认未出现任何 ERP 写请求。
