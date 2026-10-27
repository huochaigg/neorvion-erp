# ERP Copilot V10：主动业务洞察

## 已实现闭环

规则管理 → 用户主动运行 → 固定 ERP 只读 API → 确定性 Detector → Insight 去重 → Event → 站内通知。

Detector 不执行模型生成 SQL：

- `LOW_STOCK_RISK`：`quantity - reserved_quantity < threshold`。阈值是有版本审计的租户规则配置。
- `PURCHASE_ARRIVAL_DELAY`：仅使用 ERP 正式 `expected_arrival_date`，缺失日期不报警。
- `OVERDUE_SHIPMENT`：ERP 没有承诺发货日期，因此按租户配置的 processing SLA 检测，并在证据中明确
  `basis=PROCESSING_SLA`，不声称超过承诺日期。
- `INVENTORY_COVERAGE_RISK`：Decimal 计算 `可用库存 / 统计期日均有效销量`；零销量返回不适用，不猜测风险。

## 安全身份门禁

当前 IAM 仅支持用户 JWT + 当前授权快照以及带用户 JWT 的高风险权威回源，没有可供后台 Worker 使用的短期、
只读、可撤销服务身份。系统不会长期保存用户 Access Token，也不会伪造用户或使用管理员 Token。因此：

- 手动检测使用当前用户短期 Token，ERP 再次校验 audience、租户与只读权限。
- 周期 Scheduler/Worker 与 V9 LIVE Evaluation 继续禁用。
- Proposal、Approval、Execution 和 ERP 写接口不在 Detector 调用面内。

要启用后台周期检测，IAM 必须先提供带 tenant、subject、只读 scope、audience、短 TTL、撤销版本和资源白名单的
服务身份契约；ERP/Knowledge 必须独立验证该身份。

## 状态与去重

Insight 状态为 OPEN、ACKNOWLEDGED、SNOOZED、RESOLVED、CLOSED。关闭提醒不修改 ERP。Fingerprint 由
detector/resource_type/resource_id 生成；重复检测更新 `last_seen_at` 和证据，不重复创建 Insight 或通知。

## API

- `/api/v1/insight-detectors`
- `/api/v1/insight-rules`、`/{id}`、`/{id}/run`
- `/api/v1/insights`、`/dashboard`、`/{id}`、acknowledge/snooze/close/events
- `/api/v1/insight-runs`、`/{id}`
- `/api/v1/insight-notifications`、`/{id}/read`

所有列表服务端分页；所有资源查询绑定当前已验证 tenant，通知再绑定 recipient_user_id。

## 迁移与回滚

升级前备份 `neorvion_copilot`，执行 `alembic upgrade 7f803d545046`。回滚会删除全部 V10 Rule、Run、Insight、
Event 和通知数据，必须先停止服务、导出并验证备份，再执行 `alembic downgrade 20261025_0009`。

## 未声称完成的验收

未执行真实后台周期任务、真实 LLM Insight 分析、真实 LIVE Single/Multi、四服务 E2E 或浏览器 E2E；页面不会为
这些能力展示伪造数据。模型不可用不影响确定性 Insight，但当前不会生成 AI 建议。
