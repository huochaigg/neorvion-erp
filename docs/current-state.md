# 当前状态（IAM V2）

身份、会话、租户与功能 RBAC 由 `services/iam` 唯一所有。ERP 与 Knowledge 校验 IAM RS256 JWT；普通请求读 Redis DB 1 授权快照，高风险操作回源 IAM 数据库。ERP 已 DROP 遗留身份表（`20261018_0022`），只保留 `identity_name_snapshots`。不是标准 OIDC，也不宣称普通接口强一致撤权。

前端：Shell 统一登录/Refresh；`apps/iam` 与 ERP、Knowledge 同级挂到 Wujie。运维说明见 `docs/iam-operations.md`。
