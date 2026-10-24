from enum import StrEnum


class PermissionCode(StrEnum):
    COPILOT_USE = "copilot:use"
    COPILOT_APPROVE = "copilot:approve"
    PRODUCT_READ = "product:read"
    ORDER_READ = "order:read"
    INVENTORY_READ = "inventory:read"
    WAREHOUSE_READ = "warehouse:read"
    PURCHASE_READ = "purchase:read"
    AFTER_SALE_READ = "after_sale:read"
    ANALYTICS_SALES_READ = "analytics:sales:read"
    KNOWLEDGE_READ = "knowledge:read"
    PURCHASE_CREATE = "purchase:create"
    ORDER_CREATE = "order:create"
    STOCK_TRANSFER_CREATE = "stock_transfer:create"
