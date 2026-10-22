"""ERP 模型隔离登记。生产 Session 仍未切换到 TenantSession。"""

from neorvion_db import build_registry

import app.models  # noqa: F401
from app.db.base import Base

# 租户业务表由 tenant_id 非空列自动归入 tenant_scoped，不必逐个写原因。
REASONS = {
    "IdentityNameSnapshot": "IAM 用户展示名投影，没有租户列",
    "AsyncTask": "Worker 按全局 task_id 领取；空 tenant_id 表示系统任务",
    "AsyncTaskLog": "跟随任务；空租户表示系统日志",
    "OperationLog": "空 tenant_id 表示系统操作，普通接口不能列出全部企业",
    "SystemEvent": "Outbox 可含系统级事件；空租户表示系统事件",
}

REGISTRY = build_registry(Base, REASONS)
