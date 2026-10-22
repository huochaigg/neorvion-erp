"""租户隔离错误。本包不决定 HTTP 状态码，调用方自行转换。"""


class IsolationError(Exception):
    """隔离基础设施错误的基类。"""


class TenantContextRequired(IsolationError):
    """会话没有已认证的租户，或租户 ID 不是正整数。"""


class TenantRebindError(IsolationError):
    """试图在同一会话生命周期内更换租户。"""


class TenantIsolationError(IsolationError):
    """语句或写入违反租户边界。"""


class PrivilegeError(IsolationError):
    """特权会话的构造或使用超出允许范围。"""


class RegistryError(IsolationError):
    """模型登记缺失、重复或与列定义不一致。"""
