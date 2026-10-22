"""同步会话。监听器只挂在这些子类上，普通 sqlalchemy.orm.Session 保持原样。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

from neorvion_db.errors import (
    PrivilegeError,
    RegistryError,
    TenantContextRequired,
    TenantIsolationError,
    TenantRebindError,
)
from neorvion_db.policy import (
    guard_global_execute,
    guard_global_flush,
    guard_privileged_execute,
    guard_privileged_flush,
    guard_tenant_execute,
    guard_tenant_flush,
)
from neorvion_db.privileges import (
    GlobalIdentityPurpose,
    PrivilegedOperation,
    PrivilegeGrant,
    authorize_caller,
)
from neorvion_db.registry import IsolationRegistry

_GUARDS_INSTALLED = False


def _install_guards() -> None:
    """幂等注册子类事件。不监听 Session 基类，因此现有 SessionLocal 不受影响。"""
    global _GUARDS_INSTALLED
    if _GUARDS_INSTALLED:
        return
    event.listen(TenantSession, "do_orm_execute", guard_tenant_execute)
    event.listen(TenantSession, "before_flush", guard_tenant_flush)
    event.listen(GlobalIdentitySession, "do_orm_execute", guard_global_execute)
    event.listen(GlobalIdentitySession, "before_flush", guard_global_flush)
    event.listen(PrivilegedSystemSession, "do_orm_execute", guard_privileged_execute)
    event.listen(PrivilegedSystemSession, "before_flush", guard_privileged_flush)
    _GUARDS_INSTALLED = True


def _require_registry(registry: IsolationRegistry) -> IsolationRegistry:
    if not isinstance(registry, IsolationRegistry) or not registry.frozen:
        raise RegistryError("会话必须绑定已冻结的 IsolationRegistry")
    return registry


def _reject_bypass(kwargs: dict[str, Any]) -> None:
    banned = {"bypass", "skip_tenant", "reason"} & set(kwargs)
    if banned:
        names = ", ".join(sorted(banned))
        raise TenantIsolationError(f"不允许用 {names} 跳过租户隔离")


def _require_positive_tenant(tenant_id: object) -> int:
    if type(tenant_id) is not int or tenant_id <= 0:
        raise TenantContextRequired("TenantSession 必须绑定已认证的正整数 tenant_id")
    return tenant_id


class TenantSession(Session):
    """绑定单一租户的业务会话。生命周期内不能切换租户，也没有 bypass 开关。"""

    def __init__(self, tenant_id: int, *, registry: IsolationRegistry, **kwargs: Any) -> None:
        _install_guards()
        _reject_bypass(kwargs)
        bound = _require_positive_tenant(tenant_id)
        _require_registry(registry)
        kwargs.setdefault("autoflush", False)
        kwargs.setdefault("expire_on_commit", False)
        self._tenant_locked = False
        super().__init__(**kwargs)
        self._tenant_id = bound
        self._registry = registry
        self._tenant_locked = True

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_tenant_id" and getattr(self, "_tenant_locked", False):
            raise TenantRebindError("租户会话不能在生命周期内切换租户")
        super().__setattr__(name, value)

    @property
    def tenant_id(self) -> int:
        """构造时绑定的租户。不读取 session.info，避免中途改字典换成另一家企业。"""
        return self._tenant_id

    @tenant_id.setter
    def tenant_id(self, _value: int) -> None:
        raise TenantRebindError("租户会话不能在生命周期内切换租户")

    @property
    def registry(self) -> IsolationRegistry:
        return self._registry


class GlobalIdentitySession(Session):
    """IAM 用户、权限目录、平台配置等全局资源会话。不能读取租户业务表。"""

    def __init__(
        self,
        purpose: GlobalIdentityPurpose,
        *,
        registry: IsolationRegistry,
        **kwargs: Any,
    ) -> None:
        _install_guards()
        _reject_bypass(kwargs)
        if not isinstance(purpose, GlobalIdentityPurpose):
            raise TenantIsolationError(
                "全局身份会话的用途必须是 GlobalIdentityPurpose，不能是字符串"
            )
        _require_registry(registry)
        kwargs.setdefault("autoflush", False)
        kwargs.setdefault("expire_on_commit", False)
        super().__init__(**kwargs)
        self._purpose = purpose
        self._registry = registry

    @property
    def purpose(self) -> GlobalIdentityPurpose:
        return self._purpose

    @property
    def registry(self) -> IsolationRegistry:
        return self._registry


class PrivilegedSystemSession(Session):
    """Worker 领取、Outbox 扫描。没有租户，也不能仅凭持有会话就查询全部业务表。"""

    def __init__(
        self,
        grant: PrivilegeGrant,
        *,
        registry: IsolationRegistry,
        **kwargs: Any,
    ) -> None:
        _install_guards()
        _reject_bypass(kwargs)
        if not isinstance(grant, PrivilegeGrant):
            raise PrivilegeError("特权会话必须接收 PrivilegeGrant，不能接收 reason 字符串")
        _require_registry(registry)
        kwargs.setdefault("autoflush", False)
        kwargs.setdefault("expire_on_commit", False)
        super().__init__(**kwargs)
        self._operation = grant.operation
        self._registry = registry

    @property
    def operation(self) -> PrivilegedOperation:
        return self._operation

    @property
    def registry(self) -> IsolationRegistry:
        return self._registry


def open_privileged_session(
    operation: PrivilegedOperation,
    *,
    registry: IsolationRegistry,
    allowed_callers: frozenset[str],
    bind: Any = None,
    **kwargs: Any,
) -> PrivilegedSystemSession:
    """按调用方模块白名单打开特权会话。reason 字符串不能代替白名单。"""
    grant = authorize_caller(operation, allowed_callers)
    return PrivilegedSystemSession(grant, registry=registry, bind=bind, **kwargs)


def require_tenant_id(session: Session) -> int:
    """业务代码在执行前确认会话已经绑定租户。普通 Session 和全局会话都会拒绝。"""
    tenant_id = getattr(session, "tenant_id", None)
    if type(tenant_id) is not int or tenant_id <= 0:
        raise TenantContextRequired("当前会话没有已绑定的租户上下文")
    return tenant_id
