# ERP Copilot V6 受控执行

## 安全调用链

`用户确认 → Copilot 冻结 Proposal revision → 确定性审批策略 →（必要时异人审批）→ 申请人当前权限复核 → ERP Preview → ERP JWT/租户/权限 + HMAC 复核 → MySQL 单事务创建 DRAFT + Receipt → Copilot 审计`

模型只能生成和预检 Proposal，不能调用 Execution Registry。确认 nonce 只返回一次，数据库保存 SHA-256；
payload 在 Execution 创建时冻结。审批结果来自认证 HTTP API 和数据库原子状态转换，不采信 Graph resume 值。

## 状态与恢复

合法主线为 `PENDING_CONFIRMATION → WAITING_APPROVAL → APPROVED → EXECUTING → SUCCEEDED`，无需审批时跳过
WAITING。拒绝、撤销和过期进入终态；确定无副作用的校验/权限错误进入 FAILED；任何可能已经写入的超时、
网络错误或 5xx 进入 UNKNOWN。UNKNOWN 只能用同一个 execution key 查询 ERP Receipt：存在成功 Receipt 则恢复
SUCCEEDED；ERP 不可用或无确定证据时保持 UNKNOWN，不自动重试创建。

## 发布与回滚

1. 在 IAM 执行权限目录 seed，确认只有授权审批角色获得 `copilot:approve`。
2. 配置两端一致的 32+ 字节执行 Secret，先升级 ERP `20261024_0023`，再升级 Copilot `20261024_0004`。
3. 启动 Copilot 以执行官方 PostgresSaver 幂等 setup；检查 Checkpoint 表和连接权限。
4. 使用专用测试租户依次验证三类 Proposal；不得用生产业务数据。
5. 观察 UNKNOWN、幂等冲突、审批时长和 Receipt 对账，再逐租户开放。

回滚前停止新确认，等待或对账全部 EXECUTING/UNKNOWN，导出 execution/approval/attempt/audit 与 ERP Receipt。
应用可先回退到 V5 并隐藏执行入口；数据库降级会删除审计和幂等依据，生产环境通常应保留表而不是立即
downgrade。两库无法用本地事务原子回滚，任何未知执行都必须先以 ERP Receipt 为准。
