"""Knowledge 侧权限编码。真实授权仍以 ERP 目录与角色绑定为准。"""

from enum import StrEnum


class PermissionCode(StrEnum):
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_CREATE = "knowledge:create"
    KNOWLEDGE_UPDATE = "knowledge:update"
    KNOWLEDGE_DELETE = "knowledge:delete"
