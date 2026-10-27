"""IAM 模型隔离登记。用户、权限和登录会话保持全局，不因登记而加上租户条件。"""

import app.models  # noqa: F401
from app.db.base import Base
from neorvion_db import build_registry

REASONS = {
    "User": "全局身份，一个用户可以加入多个租户",
    "Permission": "平台权限目录，各企业共用同一份编码",
    "Application": "平台应用目录，没有 tenant_id",
    "Menu": "平台菜单目录，没有 tenant_id",
    "AuthSession": "登录会话属于用户，不属于单个租户",
    "Tenant": "租户实体本身没有 tenant_id 列",
    "AuditLog": "空 tenant_id 表示平台级操作，不能按单一企业过滤全部审计",
    "ServiceIdentity": "后台服务主体按白名单跨租户授权，没有单一 tenant_id 列",
    "ServiceIdentityAudit": "服务身份审计挂在服务主体上，不属于单个租户",
}

REGISTRY = build_registry(Base, REASONS)
