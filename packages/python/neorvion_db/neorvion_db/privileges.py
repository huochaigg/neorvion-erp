"""特权凭证。安全边界是枚举、封印和调用方模块，不是 reason 字符串。"""

from __future__ import annotations

import sys
from enum import StrEnum
from typing import Any

from neorvion_db.errors import PrivilegeError

# session.execute(..., execution_options={PRIVILEGED_OPERATION_KEY: operation})
PRIVILEGED_OPERATION_KEY = "neorvion_privileged_operation"
# 只放行已经人工核对过、且不读取租户业务表的工具语句。不是租户隔离开关。
REVIEWED_SQL_KEY = "neorvion_reviewed_sql"


class PrivilegedOperation(StrEnum):
    """真正的特权系统操作。不含 IAM 全局身份查询。"""

    WORKER_CLAIM = "worker_claim"
    OUTBOX_SCAN = "outbox_scan"


class ReviewedSql(StrEnum):
    """租户会话可以执行的非 ORM 工具语句。语句文本仍要再核对，枚举本身不是放行证。"""

    ADVISORY_LOCK = "advisory_lock"


class GlobalIdentityPurpose(StrEnum):
    """全局资源会话的用途。不能用来读取租户业务表。"""

    IAM_DIRECTORY = "iam_directory"
    DISPLAY_PROJECTION = "display_projection"
    PLATFORM_MODEL = "platform_model"


class _Seal:
    """只有本模块能持有的构造封印。"""


_SEAL = _Seal()


class PrivilegeGrant:
    """已通过调用方检查的特权凭证。业务代码不能用字符串伪造。"""

    __slots__ = ("operation", "_seal")

    def __init__(self, operation: PrivilegedOperation, seal: object) -> None:
        if not isinstance(operation, PrivilegedOperation):
            raise PrivilegeError("特权操作必须是 PrivilegedOperation，不能使用 reason 字符串")
        if seal is not _SEAL:
            raise PrivilegeError("特权凭证只能由 open_privileged_session 颁发")
        self.operation = operation
        self._seal = seal


def caller_module(depth: int = 1) -> str:
    """返回指定栈帧所在模块名。depth=1 是直接调用方。"""
    return str(sys._getframe(depth).f_globals.get("__name__", ""))


def authorize_caller(
    operation: PrivilegedOperation,
    allowed_callers: frozenset[str],
) -> PrivilegeGrant:
    """检查 open_* 的外部调用方，并颁发封印凭证。

    本函数只应被 open_privileged_session / open_privileged_async_session 调用。
    栈帧 2 才是业务或测试模块，栈帧 1 是这两个包装函数。
    """
    if not isinstance(operation, PrivilegedOperation):
        raise PrivilegeError("特权操作必须是 PrivilegedOperation，不能使用 reason 字符串")
    if not isinstance(allowed_callers, frozenset) or not allowed_callers:
        raise PrivilegeError("特权调用方必须是非空的模块名集合")
    caller = sys._getframe(2).f_globals.get("__name__", "")
    if caller not in allowed_callers:
        allowed = ", ".join(sorted(allowed_callers))
        raise PrivilegeError(f"模块 {caller} 不能执行 {operation.value}。允许的模块: {allowed}")
    return PrivilegeGrant(operation, _SEAL)


def reviewed_sql_option(kind: ReviewedSql) -> dict[str, Any]:
    """给咨询锁这类不访问业务表的语句使用。字符串值无效。"""
    if not isinstance(kind, ReviewedSql):
        raise PrivilegeError("已审查 SQL 必须是 ReviewedSql 枚举")
    return {REVIEWED_SQL_KEY: kind}


def privileged_option(operation: PrivilegedOperation) -> dict[str, Any]:
    """执行特权语句时必须显式带上的 execution_options。字符串值无效。"""
    if not isinstance(operation, PrivilegedOperation):
        raise PrivilegeError("特权操作必须是 PrivilegedOperation")
    return {PRIVILEGED_OPERATION_KEY: operation}
