"""异步会话适配。守卫挂在内部 sync_session 子类上，AsyncSession.execute 会触发它们。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from neorvion_db.errors import PrivilegeError, TenantIsolationError
from neorvion_db.privileges import GlobalIdentityPurpose, PrivilegeGrant, authorize_caller
from neorvion_db.registry import IsolationRegistry
from neorvion_db.sessions import GlobalIdentitySession, PrivilegedSystemSession, TenantSession


class TenantAsyncSession(AsyncSession):
    """Knowledge 请求路径使用的异步租户会话。tenant_id 转发到内部 TenantSession。"""

    def __init__(
        self,
        tenant_id: int,
        *,
        registry: IsolationRegistry,
        bind: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            bind=bind,
            sync_session_class=TenantSession,
            tenant_id=tenant_id,
            registry=registry,
            **kwargs,
        )

    @property
    def tenant_id(self) -> int:
        sync = self.sync_session
        if not isinstance(sync, TenantSession):
            raise TenantIsolationError("异步租户会话的内部会话不是 TenantSession")
        return sync.tenant_id

    @property
    def registry(self) -> IsolationRegistry:
        return self.sync_session.registry


class GlobalIdentityAsyncSession(AsyncSession):
    """异步全局身份会话。能力与 GlobalIdentitySession 相同。"""

    def __init__(
        self,
        purpose: GlobalIdentityPurpose,
        *,
        registry: IsolationRegistry,
        bind: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            bind=bind,
            sync_session_class=GlobalIdentitySession,
            purpose=purpose,
            registry=registry,
            **kwargs,
        )

    @property
    def purpose(self) -> GlobalIdentityPurpose:
        return self.sync_session.purpose

    @property
    def registry(self) -> IsolationRegistry:
        return self.sync_session.registry


class PrivilegedAsyncSession(AsyncSession):
    """异步特权会话。仍然要求 PrivilegeGrant，不能用 reason 字符串构造。"""

    def __init__(
        self,
        grant: PrivilegeGrant,
        *,
        registry: IsolationRegistry,
        bind: Any = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            bind=bind,
            sync_session_class=PrivilegedSystemSession,
            grant=grant,
            registry=registry,
            **kwargs,
        )

    @property
    def operation(self):
        """特权操作枚举。与内部 PrivilegedSystemSession 保持一致。"""
        sync = self.sync_session
        if not isinstance(sync, PrivilegedSystemSession):
            raise PrivilegeError("异步特权会话的内部会话不是 PrivilegedSystemSession")
        return sync.operation

    @property
    def registry(self) -> IsolationRegistry:
        return self.sync_session.registry


def open_privileged_async_session(
    operation,
    *,
    registry: IsolationRegistry,
    allowed_callers: frozenset[str],
    bind: Any = None,
    flush_models: frozenset[str] = frozenset(),
    **kwargs: Any,
) -> PrivilegedAsyncSession:
    """异步特权会话的唯一入口。调用方检查与同步版本相同。"""
    grant = authorize_caller(operation, allowed_callers)
    return PrivilegedAsyncSession(
        grant,
        registry=registry,
        bind=bind,
        flush_models=flush_models,
        **kwargs,
    )
