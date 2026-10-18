"""Knowledge 侧功能权限编码。目录与角色绑定由 IAM 集中配置。"""

from enum import StrEnum


class PermissionCode(StrEnum):
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_CREATE = "knowledge:create"
    KNOWLEDGE_UPDATE = "knowledge:update"
    KNOWLEDGE_DELETE = "knowledge:delete"


HIGH_RISK_PERMISSION_CODES: frozenset[str] = frozenset({PermissionCode.KNOWLEDGE_DELETE})
