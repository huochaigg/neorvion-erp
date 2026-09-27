"""平台权限编码与默认角色模板。

权限是全局目录，不是某家企业私有的：所有租户共用同一套 code。
角色是租户私有的：Acme 的 ADMIN 和 Beta 的 ADMIN 是两行，互不影响。
"""

from enum import StrEnum


class PermissionCode(StrEnum):
    TENANT_READ = "tenant:read"
    TENANT_UPDATE = "tenant:update"
    TENANT_MEMBER_READ = "tenant:member:read"
    TENANT_MEMBER_MANAGE = "tenant:member:manage"
    TENANT_ROLE_READ = "tenant:role:read"
    TENANT_ROLE_MANAGE = "tenant:role:manage"

    PRODUCT_READ = "product:read"
    PRODUCT_CREATE = "product:create"
    PRODUCT_UPDATE = "product:update"
    PRODUCT_DELETE = "product:delete"

    ORDER_READ = "order:read"
    ORDER_CREATE = "order:create"
    ORDER_AUDIT = "order:audit"
    ORDER_CANCEL = "order:cancel"

    INVENTORY_READ = "inventory:read"
    INVENTORY_INBOUND = "inventory:inbound"
    INVENTORY_OUTBOUND = "inventory:outbound"

    PURCHASE_READ = "purchase:read"
    PURCHASE_CREATE = "purchase:create"
    PURCHASE_AUDIT = "purchase:audit"


class SystemRoleCode(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    WAREHOUSE = "WAREHOUSE"
    VIEWER = "VIEWER"


# (code, name, module, description)
PERMISSION_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    (PermissionCode.TENANT_READ, "查看企业", "tenant", "查看当前企业基本信息"),
    (PermissionCode.TENANT_UPDATE, "更新企业", "tenant", "修改当前企业名称等信息"),
    (PermissionCode.TENANT_MEMBER_READ, "查看成员", "tenant", "查看当前企业成员列表"),
    (PermissionCode.TENANT_MEMBER_MANAGE, "管理成员", "tenant", "添加、启用或禁用成员"),
    (PermissionCode.TENANT_ROLE_READ, "查看角色", "tenant", "查看角色与权限定义"),
    (PermissionCode.TENANT_ROLE_MANAGE, "管理角色", "tenant", "创建、修改或删除自定义角色"),
    (PermissionCode.PRODUCT_READ, "查看商品", "product", "预留给商品模块"),
    (PermissionCode.PRODUCT_CREATE, "创建商品", "product", "预留给商品模块"),
    (PermissionCode.PRODUCT_UPDATE, "更新商品", "product", "预留给商品模块"),
    (PermissionCode.PRODUCT_DELETE, "删除商品", "product", "预留给商品模块"),
    (PermissionCode.ORDER_READ, "查看订单", "order", "预留给订单模块"),
    (PermissionCode.ORDER_CREATE, "创建订单", "order", "预留给订单模块"),
    (PermissionCode.ORDER_AUDIT, "审核订单", "order", "预留给订单模块"),
    (PermissionCode.ORDER_CANCEL, "取消订单", "order", "预留给订单模块"),
    (PermissionCode.INVENTORY_READ, "查看库存", "inventory", "预留给库存模块"),
    (PermissionCode.INVENTORY_INBOUND, "入库", "inventory", "预留给库存模块"),
    (PermissionCode.INVENTORY_OUTBOUND, "出库", "inventory", "预留给库存模块"),
    (PermissionCode.PURCHASE_READ, "查看采购", "purchase", "预留给采购模块"),
    (PermissionCode.PURCHASE_CREATE, "创建采购", "purchase", "预留给采购模块"),
    (PermissionCode.PURCHASE_AUDIT, "审核采购", "purchase", "预留给采购模块"),
)

_ALL_CODES: tuple[str, ...] = tuple(item[0] for item in PERMISSION_CATALOG)

_READ_CODES: tuple[str, ...] = (
    PermissionCode.TENANT_READ,
    PermissionCode.TENANT_MEMBER_READ,
    PermissionCode.TENANT_ROLE_READ,
    PermissionCode.PRODUCT_READ,
    PermissionCode.ORDER_READ,
    PermissionCode.INVENTORY_READ,
    PermissionCode.PURCHASE_READ,
)

# 默认角色模板。OWNER 在引导时写入目录中的全部权限；所有权语义另见 AuthorizationService。
DEFAULT_ROLE_TEMPLATES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (SystemRoleCode.OWNER, "所有者", "租户所有者，拥有全部平台权限", _ALL_CODES),
    (
        SystemRoleCode.ADMIN,
        "管理员",
        "管理企业、成员与角色，并具备后续业务模块的完整操作权限",
        _ALL_CODES,
    ),
    (
        SystemRoleCode.OPERATOR,
        "运营",
        "处理商品、订单与采购的日常操作，不能管理角色或成员",
        (
            PermissionCode.TENANT_READ,
            PermissionCode.TENANT_MEMBER_READ,
            PermissionCode.TENANT_ROLE_READ,
            PermissionCode.PRODUCT_READ,
            PermissionCode.PRODUCT_CREATE,
            PermissionCode.PRODUCT_UPDATE,
            PermissionCode.ORDER_READ,
            PermissionCode.ORDER_CREATE,
            PermissionCode.INVENTORY_READ,
            PermissionCode.PURCHASE_READ,
            PermissionCode.PURCHASE_CREATE,
        ),
    ),
    (
        SystemRoleCode.WAREHOUSE,
        "仓库",
        "处理入库出库，只读商品与订单",
        (
            PermissionCode.TENANT_READ,
            PermissionCode.PRODUCT_READ,
            PermissionCode.ORDER_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.INVENTORY_INBOUND,
            PermissionCode.INVENTORY_OUTBOUND,
        ),
    ),
    (
        SystemRoleCode.VIEWER,
        "只读",
        "只能查看，不能改数据或管理成员",
        _READ_CODES,
    ),
)


def known_permission_codes() -> frozenset[str]:
    return frozenset(_ALL_CODES)


def ensure_known_permission(code: str) -> str:
    """权限编码不存在是服务端配置错误，不能悄悄放行。"""
    if code not in known_permission_codes():
        raise ValueError(f"未定义的权限编码: {code}")
    return code
