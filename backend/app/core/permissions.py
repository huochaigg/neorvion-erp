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
    ORDER_UPDATE = "order:update"
    ORDER_SUBMIT = "order:submit"
    ORDER_AUDIT = "order:audit"
    ORDER_CANCEL = "order:cancel"

    CUSTOMER_READ = "customer:read"
    CUSTOMER_CREATE = "customer:create"
    CUSTOMER_UPDATE = "customer:update"
    CUSTOMER_DISABLE = "customer:disable"
    CUSTOMER_DELETE = "customer:delete"

    INVENTORY_READ = "inventory:read"
    INVENTORY_INITIALIZE = "inventory:initialize"
    INVENTORY_ADJUST = "inventory:adjust"
    INVENTORY_TRANSACTION_READ = "inventory:transaction:read"
    INVENTORY_INBOUND = "inventory:inbound"
    INVENTORY_OUTBOUND = "inventory:outbound"

    WAREHOUSE_READ = "warehouse:read"
    WAREHOUSE_CREATE = "warehouse:create"
    WAREHOUSE_UPDATE = "warehouse:update"
    WAREHOUSE_DISABLE = "warehouse:disable"
    WAREHOUSE_DELETE = "warehouse:delete"

    PURCHASE_READ = "purchase:read"
    PURCHASE_CREATE = "purchase:create"
    PURCHASE_UPDATE = "purchase:update"
    PURCHASE_SUBMIT = "purchase:submit"
    PURCHASE_AUDIT = "purchase:audit"
    PURCHASE_CANCEL = "purchase:cancel"
    PURCHASE_RECEIPT_READ = "purchase:receipt:read"
    PURCHASE_RECEIPT_CREATE = "purchase:receipt:create"
    PURCHASE_RECEIPT_UPDATE = "purchase:receipt:update"
    PURCHASE_RECEIPT_CONFIRM = "purchase:receipt:confirm"
    PURCHASE_RECEIPT_CANCEL = "purchase:receipt:cancel"

    OUTBOUND_READ = "outbound:read"
    OUTBOUND_CREATE = "outbound:create"
    OUTBOUND_PICK = "outbound:pick"
    OUTBOUND_CONFIRM = "outbound:confirm"
    OUTBOUND_CANCEL = "outbound:cancel"

    SUPPLIER_READ = "supplier:read"
    SUPPLIER_CREATE = "supplier:create"
    SUPPLIER_UPDATE = "supplier:update"
    SUPPLIER_DISABLE = "supplier:disable"
    SUPPLIER_DELETE = "supplier:delete"


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
    (PermissionCode.ORDER_READ, "查看订单", "order", "查看销售订单列表与详情"),
    (PermissionCode.ORDER_CREATE, "创建订单", "order", "创建草稿销售订单"),
    (PermissionCode.ORDER_UPDATE, "编辑订单", "order", "编辑草稿销售订单"),
    (PermissionCode.ORDER_SUBMIT, "提交订单", "order", "提交销售订单进入待确认"),
    (PermissionCode.ORDER_AUDIT, "审核订单", "order", "确认销售订单并预占库存"),
    (PermissionCode.ORDER_CANCEL, "取消订单", "order", "取消销售订单；待出库时释放预占"),
    (PermissionCode.CUSTOMER_READ, "查看客户", "customer", "查看本企业客户"),
    (PermissionCode.CUSTOMER_CREATE, "新增客户", "customer", "创建客户"),
    (PermissionCode.CUSTOMER_UPDATE, "编辑客户", "customer", "编辑客户档案，编码创建后只读"),
    (PermissionCode.CUSTOMER_DISABLE, "启用停用客户", "customer", "启用或禁用客户"),
    (PermissionCode.CUSTOMER_DELETE, "删除客户", "customer", "删除尚未被销售订单引用的客户"),
    (PermissionCode.INVENTORY_READ, "查看库存", "inventory", "查看库存台账"),
    (PermissionCode.INVENTORY_INITIALIZE, "初始化库存", "inventory", "给仓库 + SKU 写入首次库存"),
    (PermissionCode.INVENTORY_ADJUST, "调整库存", "inventory", "盘点增加或减少实际库存"),
    (
        PermissionCode.INVENTORY_TRANSACTION_READ,
        "查看库存流水",
        "inventory",
        "查看库存变化历史",
    ),
    (PermissionCode.INVENTORY_INBOUND, "入库", "inventory", "预留给收货入库"),
    (PermissionCode.INVENTORY_OUTBOUND, "出库", "inventory", "预留给销售出库"),
    (PermissionCode.WAREHOUSE_READ, "查看仓库", "warehouse", "查看本企业仓库档案"),
    (PermissionCode.WAREHOUSE_CREATE, "新增仓库", "warehouse", "创建仓库"),
    (PermissionCode.WAREHOUSE_UPDATE, "编辑仓库", "warehouse", "编辑仓库档案并设置默认仓库"),
    (PermissionCode.WAREHOUSE_DISABLE, "启用停用仓库", "warehouse", "启用或禁用仓库"),
    (PermissionCode.WAREHOUSE_DELETE, "删除仓库", "warehouse", "删除尚未被业务引用的仓库"),
    (PermissionCode.PURCHASE_READ, "查看采购单", "purchase", "查看采购单列表与详情"),
    (PermissionCode.PURCHASE_CREATE, "新建采购单", "purchase", "创建草稿采购单"),
    (PermissionCode.PURCHASE_UPDATE, "编辑采购单", "purchase", "编辑草稿或驳回后的采购单"),
    (PermissionCode.PURCHASE_SUBMIT, "提交采购审核", "purchase", "提交或重新提交采购单审核"),
    (PermissionCode.PURCHASE_AUDIT, "审核采购单", "purchase", "审核通过或驳回采购单"),
    (PermissionCode.PURCHASE_CANCEL, "取消采购单", "purchase", "取消草稿、待审核或已驳回的采购单"),
    (PermissionCode.PURCHASE_RECEIPT_READ, "查看收货单", "purchase", "查看采购收货单"),
    (PermissionCode.PURCHASE_RECEIPT_CREATE, "新建收货单", "purchase", "创建收货草稿"),
    (PermissionCode.PURCHASE_RECEIPT_UPDATE, "编辑收货单", "purchase", "修改草稿收货数量"),
    (PermissionCode.PURCHASE_RECEIPT_CONFIRM, "确认收货", "purchase", "确认收货并增加库存"),
    (PermissionCode.PURCHASE_RECEIPT_CANCEL, "取消收货单", "purchase", "作废尚未入库的收货草稿"),
    (PermissionCode.OUTBOUND_READ, "查看出库单", "outbound", "查看销售出库单"),
    (PermissionCode.OUTBOUND_CREATE, "创建出库单", "outbound", "为待出库订单生成出库任务"),
    (PermissionCode.OUTBOUND_PICK, "拣货", "outbound", "确认拣货数量，不扣库存"),
    (PermissionCode.OUTBOUND_CONFIRM, "确认出库", "outbound", "正式扣减实际库存和预占"),
    (PermissionCode.OUTBOUND_CANCEL, "取消出库单", "outbound", "取消尚未出库的拣货任务"),
    (PermissionCode.SUPPLIER_READ, "查看供应商", "supplier", "查看本企业供应商"),
    (PermissionCode.SUPPLIER_CREATE, "新增供应商", "supplier", "创建供应商"),
    (PermissionCode.SUPPLIER_UPDATE, "编辑供应商", "supplier", "编辑供应商档案，编码创建后只读"),
    (PermissionCode.SUPPLIER_DISABLE, "启用停用供应商", "supplier", "启用或禁用供应商"),
    (PermissionCode.SUPPLIER_DELETE, "删除供应商", "supplier", "删除尚未被采购单引用的供应商"),
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
    PermissionCode.CUSTOMER_READ,
    PermissionCode.INVENTORY_READ,
    PermissionCode.INVENTORY_TRANSACTION_READ,
    PermissionCode.WAREHOUSE_READ,
    PermissionCode.PURCHASE_READ,
    PermissionCode.PURCHASE_RECEIPT_READ,
    PermissionCode.OUTBOUND_READ,
    PermissionCode.SUPPLIER_READ,
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
            PermissionCode.ORDER_UPDATE,
            PermissionCode.ORDER_SUBMIT,
            PermissionCode.ORDER_CANCEL,
            PermissionCode.CUSTOMER_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.INVENTORY_TRANSACTION_READ,
            PermissionCode.WAREHOUSE_READ,
            PermissionCode.SUPPLIER_READ,
            PermissionCode.PURCHASE_READ,
            PermissionCode.PURCHASE_CREATE,
            PermissionCode.PURCHASE_UPDATE,
            PermissionCode.PURCHASE_SUBMIT,
            PermissionCode.PURCHASE_CANCEL,
            PermissionCode.PURCHASE_RECEIPT_READ,
            PermissionCode.PURCHASE_RECEIPT_CREATE,
            PermissionCode.OUTBOUND_READ,
        ),
    ),
    (
        SystemRoleCode.WAREHOUSE,
        "仓库",
        "维护仓库档案，处理入库出库，只读商品与订单",
        (
            PermissionCode.TENANT_READ,
            PermissionCode.PRODUCT_READ,
            PermissionCode.ORDER_READ,
            PermissionCode.INVENTORY_READ,
            PermissionCode.INVENTORY_INITIALIZE,
            PermissionCode.INVENTORY_ADJUST,
            PermissionCode.INVENTORY_TRANSACTION_READ,
            PermissionCode.INVENTORY_INBOUND,
            PermissionCode.INVENTORY_OUTBOUND,
            PermissionCode.WAREHOUSE_READ,
            PermissionCode.WAREHOUSE_CREATE,
            PermissionCode.WAREHOUSE_UPDATE,
            PermissionCode.SUPPLIER_READ,
            PermissionCode.PURCHASE_READ,
            PermissionCode.PURCHASE_RECEIPT_READ,
            PermissionCode.PURCHASE_RECEIPT_CREATE,
            PermissionCode.PURCHASE_RECEIPT_UPDATE,
            PermissionCode.PURCHASE_RECEIPT_CONFIRM,
            PermissionCode.PURCHASE_RECEIPT_CANCEL,
            PermissionCode.OUTBOUND_READ,
            PermissionCode.OUTBOUND_CREATE,
            PermissionCode.OUTBOUND_PICK,
            PermissionCode.OUTBOUND_CONFIRM,
            PermissionCode.OUTBOUND_CANCEL,
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
                title="销售订单",
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
                        title="新建",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:order-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:order-submit",
                        title="提交",
                        type="ACTION",
                        permission_code=PermissionCode.ORDER_SUBMIT,
                    ),
                    PermissionTreeDef(
                        key="action:order-audit",
                        title="审核 / 确认",
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
            PermissionTreeDef(
                key="menu:customers",
                title="客户管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:customer-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.CUSTOMER_READ,
                    ),
                    PermissionTreeDef(
                        key="action:customer-create",
                        title="新建",
                        type="ACTION",
                        permission_code=PermissionCode.CUSTOMER_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:customer-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.CUSTOMER_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:customer-disable",
                        title="启用 / 禁用",
                        type="ACTION",
                        permission_code=PermissionCode.CUSTOMER_DISABLE,
                    ),
                    PermissionTreeDef(
                        key="action:customer-delete",
                        title="删除",
                        type="ACTION",
                        permission_code=PermissionCode.CUSTOMER_DELETE,
                    ),
                ),
            ),
        ),
    ),
    PermissionTreeDef(
        key="dir:warehouse",
        title="仓库管理",
        type="DIRECTORY",
        children=(
            PermissionTreeDef(
                key="menu:warehouses",
                title="仓库管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:warehouse-read",
                        title="查看仓库",
                        type="ACTION",
                        permission_code=PermissionCode.WAREHOUSE_READ,
                    ),
                    PermissionTreeDef(
                        key="action:warehouse-create",
                        title="新增仓库",
                        type="ACTION",
                        permission_code=PermissionCode.WAREHOUSE_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:warehouse-update",
                        title="编辑仓库",
                        type="ACTION",
                        permission_code=PermissionCode.WAREHOUSE_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:warehouse-disable",
                        title="启用 / 禁用",
                        type="ACTION",
                        permission_code=PermissionCode.WAREHOUSE_DISABLE,
                    ),
                    PermissionTreeDef(
                        key="action:warehouse-delete",
                        title="删除仓库",
                        type="ACTION",
                        permission_code=PermissionCode.WAREHOUSE_DELETE,
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
                        title="查看库存",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_READ,
                    ),
                    PermissionTreeDef(
                        key="action:inventory-initialize",
                        title="初始化库存",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_INITIALIZE,
                    ),
                    PermissionTreeDef(
                        key="action:inventory-adjust",
                        title="调整库存",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_ADJUST,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:inventory-transactions",
                title="库存流水",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:inventory-transaction-read",
                        title="查看库存流水",
                        type="ACTION",
                        permission_code=PermissionCode.INVENTORY_TRANSACTION_READ,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:outbound",
                title="销售出库",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:outbound-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.OUTBOUND_READ,
                    ),
                    PermissionTreeDef(
                        key="action:outbound-create",
                        title="创建",
                        type="ACTION",
                        permission_code=PermissionCode.OUTBOUND_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:outbound-pick",
                        title="拣货",
                        type="ACTION",
                        permission_code=PermissionCode.OUTBOUND_PICK,
                    ),
                    PermissionTreeDef(
                        key="action:outbound-confirm",
                        title="确认出库",
                        type="ACTION",
                        permission_code=PermissionCode.OUTBOUND_CONFIRM,
                    ),
                    PermissionTreeDef(
                        key="action:outbound-cancel",
                        title="取消",
                        type="ACTION",
                        permission_code=PermissionCode.OUTBOUND_CANCEL,
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
                title="采购单",
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
                        title="新建",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:purchase-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:purchase-submit",
                        title="提交审核",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_SUBMIT,
                    ),
                    PermissionTreeDef(
                        key="action:purchase-audit",
                        title="审核",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_AUDIT,
                    ),
                    PermissionTreeDef(
                        key="action:purchase-cancel",
                        title="取消",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_CANCEL,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:purchase-receipts",
                title="采购收货",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:receipt-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_RECEIPT_READ,
                    ),
                    PermissionTreeDef(
                        key="action:receipt-create",
                        title="新建",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_RECEIPT_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:receipt-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_RECEIPT_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:receipt-confirm",
                        title="确认收货",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_RECEIPT_CONFIRM,
                    ),
                    PermissionTreeDef(
                        key="action:receipt-cancel",
                        title="取消",
                        type="ACTION",
                        permission_code=PermissionCode.PURCHASE_RECEIPT_CANCEL,
                    ),
                ),
            ),
            PermissionTreeDef(
                key="menu:suppliers",
                title="供应商管理",
                type="MENU",
                children=(
                    PermissionTreeDef(
                        key="action:supplier-read",
                        title="查看",
                        type="ACTION",
                        permission_code=PermissionCode.SUPPLIER_READ,
                    ),
                    PermissionTreeDef(
                        key="action:supplier-create",
                        title="新建",
                        type="ACTION",
                        permission_code=PermissionCode.SUPPLIER_CREATE,
                    ),
                    PermissionTreeDef(
                        key="action:supplier-update",
                        title="编辑",
                        type="ACTION",
                        permission_code=PermissionCode.SUPPLIER_UPDATE,
                    ),
                    PermissionTreeDef(
                        key="action:supplier-disable",
                        title="启用 / 禁用",
                        type="ACTION",
                        permission_code=PermissionCode.SUPPLIER_DISABLE,
                    ),
                    PermissionTreeDef(
                        key="action:supplier-delete",
                        title="删除",
                        type="ACTION",
                        permission_code=PermissionCode.SUPPLIER_DELETE,
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
