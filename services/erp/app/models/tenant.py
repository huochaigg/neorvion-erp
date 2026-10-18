"""租户相关枚举。Tenant / TenantMember 表已迁到 IAM，ERP 不再建身份表。"""

from enum import StrEnum


class TenantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MemberStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class MemberRole(StrEnum):
    """成员所有权标记。细粒度权限在 IAM 角色上，本枚举只区分 OWNER / MEMBER。"""

    OWNER = "OWNER"
    MEMBER = "MEMBER"
