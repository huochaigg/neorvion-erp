from enum import StrEnum


class PermissionCode(StrEnum):
    COPILOT_USE = "copilot:use"
    PRODUCT_READ = "product:read"
    ORDER_READ = "order:read"
    INVENTORY_READ = "inventory:read"
    WAREHOUSE_READ = "warehouse:read"
    PURCHASE_READ = "purchase:read"
    AFTER_SALE_READ = "after_sale:read"
