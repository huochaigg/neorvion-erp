# 当前状态（V12）

身份、租户与功能 RBAC 由 `services/iam` 唯一所有。ERP 与 Knowledge 校验 IAM RS256 JWT，并从 Redis DB 1 读取授权快照，不再互为认证中心。

前端：Shell 统一登录/Refresh；`apps/iam` 与 ERP、Knowledge 同级挂到 Wujie。
