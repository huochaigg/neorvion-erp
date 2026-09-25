from contextvars import ContextVar

current_tenant_id: ContextVar[int | None] = ContextVar("current_tenant_id", default=None)
current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def get_current_tenant_id() -> int | None:
    return current_tenant_id.get()


def set_tenant_context(*, tenant_id: int | None, user_id: int | None) -> None:
    """后续 Redis、操作日志、后台任务统一读取这里的租户上下文。"""
    current_tenant_id.set(tenant_id)
    current_user_id.set(user_id)
