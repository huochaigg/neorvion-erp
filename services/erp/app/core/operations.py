"""操作日志动作编码。记录「谁做了什么」，不是业务事件本身。"""

from enum import StrEnum


class OperationAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    SUBMIT = "SUBMIT"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    CONFIRM = "CONFIRM"
    CANCEL = "CANCEL"
    LOGIN = "LOGIN"
    LOGOUT = "LOGOUT"
    EXPORT = "EXPORT"
    RETRY = "RETRY"


class OperationResult(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class OperationModule(StrEnum):
    AUTH = "auth"
    ORDER = "order"
    PURCHASE = "purchase"
    PURCHASE_RECEIPT = "purchase_receipt"
    OUTBOUND = "outbound"
    INVENTORY = "inventory"
    SHIPMENT = "shipment"
    AFTER_SALE = "after_sale"
    REFUND = "refund"
    PURCHASE_RETURN = "purchase_return"
    STOCK_TRANSFER = "stock_transfer"
    ANALYTICS = "analytics"
    TASK = "task"
