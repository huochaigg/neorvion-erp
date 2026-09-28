"""平台权限编码、默认角色模板与权限树。

权限是全局目录，不是某家企业私有的：所有租户共用同一套 code。
角色是租户私有的：Acme 的 ADMIN 和 Beta 的 ADMIN 是两行，互不影响。

PermissionCode 表示代码真实支持的能力，不是某个角色的固定清单。
role_permissions 才表示某个租户角色实际拥有哪些目录项。
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class PermissionCode(StrEnum):
    TENANT_READ = "tenant:read"
    TENANT_UPDATE = "tenant:update"

    TENANT_MEMBER_READ = "tenant:member:read"
    TENANT_MEMBER_CREATE = "tenant:member:create"
    TENANT_MEMBER_UPDATE = "tenant:member:update"
    TENANT_MEMBER_ROLE_UPDATE = "tenant:member:role:update"
    TENANT_MEMBER_DISABLE = "tenant:member:disable"
    TENANT_MEMBER_REMOVE = "tenant:member:remove"
    # 旧粗粒度权限，保留兼容，不再用于新接口校验。
    TENANT_MEMBER_MANAGE = "tenant:member:manage"

    TENANT_ROLE_READ = "tenant:role:read"
    TENANT_ROLE_CREATE = "tenant:role:create"
    TENANT_ROLE_UPDATE = "tenant:role:update"
    TENANT_ROLE_DELETE = "tenant:role:delete"
    TENANT_ROLE_PERMISSION_UPDATE = "tenant:role:permission:update"
    TENANT_ROLE_MANAGE = "tenant:role:manage"

    TENANT_PERMISSION_READ = "tenant:permission:read"

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


ResourceType = Literal["DIRECTORY", "MENU", "ACTION"]


@dataclass(frozen=True)
class PermissionTreeDef:
    """权限配置 UI 节点。DIRECTORY / 纯分组 MENU 没有 PermissionCode，不能写进 role_permissions。"""

    key: str
    title: str
    type: ResourceType
    permission_code: str | None = None
    children: tuple["PermissionTreeDef", ...] = ()


# (code, name, module, description)
PERMISSION_CATALOG: tuple[tuple[str, str, str, str], ...] = (
    (PermissionCode.TENANT_READ, "查看企业", "tenant", "查看当前企业基本信息"),
    (PermissionCode.TENANT_UPDATE, "更新企业", "tenant", "修改当前企业名称等信息"),
    (PermissionCode.TENANT_MEMBER_READ, "查看成员", "tenant", "查看当前企业成员列表"),
    (PermissionCode.TENANT_MEMBER_CREATE, "添加成员", "tenant", "添加已有账号或创建企业登录账号"),
    (PermissionCode.TENANT_MEMBER_UPDATE, "编辑成员", "tenant", "修改企业内显示名称"),
    (
        PermissionCode.TENANT_MEMBER_ROLE_UPDATE,
        "修改成员角色",
        "tenant",
        "调整成员在当前企业的角色",
    ),
    (
        PermissionCode.TENANT_MEMBER_DISABLE,
        "禁用成员",
        "tenant",
        "启用或禁用成员，不解除成员关系",
    ),
    (
        PermissionCode.TENANT_MEMBER_REMOVE,
        "移除成员",
        "tenant",
        "解除当前企业成员关系，不删除全局账号",
    ),
    (
        PermissionCode.TENANT_MEMBER_MANAGE,
        "管理成员（兼容）",
        "tenant",
        "旧粗粒度权限，已拆分为创建/编辑/改角色/禁用/移除",
    ),
    (PermissionCode.TENANT_ROLE_READ, "查看角色", "tenant", "查看角色与权限定义"),
    (PermissionCode.TENANT_ROLE_CREATE, "新建角色", "tenant", "创建自定义角色"),
    (PermissionCode.TENANT_ROLE_UPDATE, "编辑角色", "tenant", "修改自定义角色名称与说明"),
    (PermissionCode.TENANT_ROLE_DELETE, "删除角色", "tenant", "删除未被成员使用的自定义角色"),
    (
        PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
        "配置角色权限",
        "tenant",
        "替换角色拥有的权限集合",
    ),
    (
        PermissionCode.TENANT_ROLE_MANAGE,
        "管理角色（兼容）",
        "tenant",
        "旧粗粒度权限，已拆分为创建/编辑/删除/配置权限",
    ),
    (PermissionCode.TENANT_PERMISSION_READ, "查看权限", "tenant", "查看平台权限目录"),
    (PermissionCode.PRODUCT_READ, "查看商品", "product", "查看商品、类目与品牌"),
    (PermissionCode.PRODUCT_CREATE, "创建商品", "product", "创建商品 SPU 及初始 SKU"),
    (PermissionCode.PRODUCT_UPDATE, "更新商品", "product", "编辑商品、SKU、类目与品牌"),
    (PermissionCode.PRODUCT_DELETE, "删除商品", "product", "删除未被引用的类目、品牌；停用商品"),
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

DEPRECATED_PERMISSION_CODES: frozenset[str] = frozenset(
    {
        PermissionCode.TENANT_MEMBER_MANAGE,
        PermissionCode.TENANT_ROLE_MANAGE,
    }
)

# 拥有旧 manage 的角色补上对应细粒度权限，旧 code 本身不删，避免历史数据断裂。
LEGACY_MANAGE_EXPANSION: dict[str, tuple[str, ...]] = {
    PermissionCode.TENANT_MEMBER_MANAGE: (
        PermissionCode.TENANT_MEMBER_CREATE,
        PermissionCode.TENANT_MEMBER_UPDATE,
        PermissionCode.TENANT_MEMBER_ROLE_UPDATE,
        PermissionCode.TENANT_MEMBER_DISABLE,
        PermissionCode.TENANT_MEMBER_REMOVE,
    ),
    PermissionCode.TENANT_ROLE_MANAGE: (
        PermissionCode.TENANT_ROLE_CREATE,
        PermissionCode.TENANT_ROLE_UPDATE,
        PermissionCode.TENANT_ROLE_DELETE,
        PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
    ),
}

_ALL_CODES: tuple[str, ...] = tuple(item[0] for item in PERMISSION_CATALOG)

_READ_CODES: tuple[str, ...] = (
    PermissionCode.TENANT_READ,
    PermissionCode.TENANT_MEMBER_READ,
    PermissionCode.TENANT_ROLE_READ,
    PermissionCode.TENANT_PERMISSION_READ,
    PermissionCode.PRODUCT_READ,
    PermissionCode.ORDER_READ,
    PermissionCode.INVENTORY_READ,
    PermissionCode.PURCHASE_READ,
)

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
            PermissionCode.TENANT_PERMISSION_READ,
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

ADMIN_REQUIRED_PERMISSION_CODES: frozenset[str] = frozenset(
    {
        PermissionCode.TENANT_READ,
        PermissionCode.TENANT_UPDATE,
        PermissionCode.TENANT_MEMBER_READ,
        PermissionCode.TENANT_MEMBER_CREATE,
        PermissionCode.TENANT_MEMBER_UPDATE,
        PermissionCode.TENANT_MEMBER_ROLE_UPDATE,
        PermissionCode.TENANT_MEMBER_DISABLE,
        PermissionCode.TENANT_MEMBER_REMOVE,
        PermissionCode.TENANT_ROLE_READ,
        PermissionCode.TENANT_ROLE_CREATE,
        PermissionCode.TENANT_ROLE_UPDATE,
        PermissionCode.TENANT_ROLE_DELETE,
        PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
        PermissionCode.TENANT_PERMISSION_READ,
    }
)

PERMISSION_TREE: tuple[PermissionTreeDef, ...] = (
    PermissionTreeDef(
        key="dir:system",
        title="系统管理",
        type="DIRECTORY",
        children=(
            PermissionTreeDef(
                key="menu:members",
                title="成员管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:member-read",
                        title="查看成员",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_MEMBER_READ,
                    ),
                    PermissionTreeDef(
                        key="action:member-create",
                        title="添加成员",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_MEMBER_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:member-update",
                        title="编辑成员",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_MEMBER_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:member-role-update",
                        title="修改角色",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_MEMBER_ROLE_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:member-disable",
                        title="禁用成员",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_MEMBER_DISABLE,
                    ),
                    PermissionTreeDef(
                        key="action:member-remove",
                        title="移除成员",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_MEMBER_REMOVE,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:roles",
                title="角色管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:role-read",
                        title="查看角色",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_ROLE_READ,
                    ),
                    PermissionTreeDef(
                        key="action:role-create",
                        title="新建角色",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_ROLE_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:role-update",
                        title="编辑角色",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_ROLE_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:role-delete",
                        title="删除角色",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_ROLE_DELETE,
                    ),
                    PermissionTreeDef(
                        key="action:role-permission-update",
                        title="配置权限",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_ROLE_PERMISSION_UPDATE,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:permissions",
                title="权限目录",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:permission-read",
                        title="查看权限",
                        type="ACTION",
                        permission_code=PermissionCode.TENANT_PERMISSION_READ,
                    ),
                ),
            ),
        ),
    ),
    PermissionTreeDef(
        key="dir:product",
        title="商品管理",
        type="DIRECTORY",
        children=(
            PermissionTreeDef(
                key="menu:products",
                title="商品列表",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:product-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_READ,
                    ),
                    PermissionTreeDef(
                        key="action:product-create",
                        title="新建",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:product-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:product-delete",
                        title="删除",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_DELETE,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:product-categories",
                title="类目管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:product-category-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_READ,
                    ),
                    PermissionTreeDef(
                        key="action:product-category-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:product-category-delete",
                        title="删除",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_DELETE,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:brands",
                title="品牌管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:product-brand-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_READ,
                    ),
                    PermissionTreeDef(
                        key="action:product-brand-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:product-brand-delete",
                        title="删除",
                        type="ACTION",
                        permission_code=PermissionCode.PRODUCT_DELETE,
                    ),
                ),
            ),
        ),
    ),
    PermissionTreeDef(
        key="dir:order",
        title="订单管理",
        type="DIRECTORY",
        children=(
            PermissionTreeDef(
                key="menu:orders",
                title="订单列表",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:order-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_READ,
                    ),
                    PermissionTreeDef(
                        key="action:order-create",
                        title="创建",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:order-audit",
                        title="审核",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_AUDIT,
                    ),
                    PermissionTreeDef(
                        key="action:order-cancel",
                        title="取消",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_CANCEL,
                    ),
                ),
            ),
        ),
    ),
    PermissionTreeDef(
        key="dir:inventory",
        title="库存管理",
        type="DIRECTORY",
        children=(
            PermissionTreeDef(
                key="menu:inventory",
                title="库存列表",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:inventory-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_READ,
                    ),
                    PermissionTreeDef(
                        key="action:inventory-inbound",
                        title="入库",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_INBOUND,
                    ),
                    PermissionTreeDef(
                        key="action:inventory-outbound",
                        title="出库",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_OUTBOUND,
                    ),
                ),
            ),
        ),
    ),
    PermissionTreeDef(
        key="dir:purchase",
        title="采购管理",
        type="DIRECTORY",
        children=(
            PermissionTreeDef(
                key="menu:purchase",
                title="采购列表",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:purchase-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_READ,
                    ),
                    PermissionTreeDef(
                        key="action:purchase-create",
                        title="创建",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:purchase-audit",
                        title="审核",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_AUDIT,
                    ),
                ),
            ),
        ),
    ),
)


def known_permission_codes() -> frozenset[str]:
    return frozenset(_ALL_CODES)


def is_deprecated_permission(code: str) -> bool:
    return code in DEPRECATED_PERMISSION_CODES


def ensure_known_permission(code: str) -> str:
    """权限编码不存在是服务端配置错误，不能悄悄放行。"""
    if code not in known_permission_codes():
        raise ValueError(f"未定义的权限编码: {code}")
    return code
