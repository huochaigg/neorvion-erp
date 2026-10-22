"""IAM 全局身份查询登记。这些函数按原有业务规则访问，不视为漏写租户条件。"""

from neorvion_db import AllowedQuery

ALLOWLIST = (
    AllowedQuery(
        "rbac.py:PermissionRepository.list_all",
        "权限目录是全局资源，各企业共用同一份编码",
    ),
    AllowedQuery(
        "rbac.py:PermissionRepository.get_by_code",
        "按全局权限编码查找，权限表没有 tenant_id",
    ),
    AllowedQuery(
        "rbac.py:PermissionRepository.get_by_ids",
        "按全局权限主键批量读取，权限表没有 tenant_id",
    ),
    AllowedQuery(
        "tenant.py:TenantMemberRepository.get_by_id",
        "按成员主键读取且当前无路由调用，登记以免以后漏加租户条件",
    ),
    AllowedQuery(
        "tenant.py:TenantMemberRepository.list_for_user",
        "列出当前用户加入的全部企业，结果按 user_id 而不是单一租户",
    ),
    AllowedQuery(
        "tenant.py:TenantRepository.get_by_code",
        "按租户编码读取租户实体，该表没有 tenant_id 列",
    ),
    AllowedQuery(
        "tenant.py:TenantRepository.get_by_id",
        "按主键读取租户实体，参数名 tenant_id 是租户自己的 id",
    ),
    AllowedQuery(
        "user.py:UserRepository.get_by_email",
        "登录按全局邮箱查找用户，用户表没有 tenant_id",
    ),
    AllowedQuery(
        "user.py:UserRepository.get_by_id",
        "按全局用户主键读取身份，用户表没有 tenant_id",
    ),
)
