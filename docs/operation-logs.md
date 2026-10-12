# 操作日志

`OperationLog` 是应用层审计：哪个用户、在哪个租户、对哪个资源、做了什么动作。

它不等于：

- `SystemEvent`（业务事实）
- MySQL binlog / Audit Plugin（数据库层变更）

## 记录什么

成功的关键业务动作与主事务一起写入（`result=SUCCESS`）。业务 rollback 后用独立 Session 写 `FAILED`，避免失败尝试没有痕迹。

动作编码稳定：`CREATE` / `CONFIRM` / `APPROVE` / `CANCEL` / `EXPORT` / `RETRY`。自然语言放在 `description`。

## 脱敏

默认不保存完整 request body。禁止：

- password / encrypted_password
- token / Authorization / cookie
- 支付密钥、RSA 私钥

## request_id

每个 HTTP 请求生成或复用合法 `X-Request-ID`，写入响应头和操作日志，便于前端报错、后端日志、审计三方对照。V14 不做 OpenTelemetry。

## 权限

只能查询，不能修改或删除。默认 OWNER / ADMIN 可看。VIEWER 不可看（含操作人信息）。
