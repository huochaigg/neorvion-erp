"""Knowledge 模型隔离登记。业务请求使用 TenantAsyncSession，SessionLocal 保持普通 AsyncSession。"""

from neorvion_db import build_registry

import app.models  # noqa: F401
from app.db.base import Base

REASONS = {
    "ModelProfile": "平台模型配置，没有 tenant_id",
}

REGISTRY = build_registry(Base, REASONS)
