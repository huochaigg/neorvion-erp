"""模型隔离登记。分类以列定义为准，全局表和混合表必须写明原因。"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from neorvion_db.errors import RegistryError


class IsolationClass(StrEnum):
    """表在租户隔离中的类别。"""

    TENANT_SCOPED = "tenant_scoped"
    GLOBAL = "global"
    NULLABLE_TENANT = "nullable_tenant"


@dataclass(frozen=True, slots=True)
class ModelRegistration:
    """一个 ORM 类的隔离分类。"""

    model: type
    isolation: IsolationClass
    table_name: str
    reason: str


class IsolationRegistry:
    """进程内模型登记表。冻结后不能再改，避免运行中偷偷改分类。"""

    def __init__(self) -> None:
        self._by_model: dict[type, ModelRegistration] = {}
        self._frozen = False

    def register(
        self,
        model: type,
        isolation: IsolationClass,
        *,
        reason: str = "",
    ) -> None:
        """登记一个映射类。同一类不能登记两次。"""
        if self._frozen:
            raise RegistryError(f"登记表已冻结，不能再加入 {model!r}")
        if not isinstance(isolation, IsolationClass):
            raise RegistryError("isolation 必须是 IsolationClass 枚举")
        table = getattr(model, "__table__", None)
        if table is None:
            raise RegistryError(f"{model!r} 不是已映射的 ORM 类")
        if model in self._by_model:
            raise RegistryError(f"{model.__name__} 已登记")
        self._by_model[model] = ModelRegistration(
            model=model,
            isolation=isolation,
            table_name=table.name,
            reason=reason.strip(),
        )

    def freeze(self) -> None:
        """登记完成后调用。V2 会话只接受冻结的登记表。"""
        self._frozen = True

    @property
    def frozen(self) -> bool:
        return self._frozen

    def get(self, model: type) -> ModelRegistration | None:
        return self._by_model.get(model)

    def require(self, model: type) -> ModelRegistration:
        """未登记的映射类按失败即拒绝处理，不能当成全局表放行。"""
        found = self._by_model.get(model)
        if found is None:
            name = getattr(model, "__name__", repr(model))
            raise RegistryError(f"模型 {name} 未做隔离登记")
        return found

    def registrations(self) -> tuple[ModelRegistration, ...]:
        return tuple(self._by_model.values())

    def summary(self) -> dict[str, list[str]]:
        """按类别返回表名，便于核对三个服务的登记结果。"""
        grouped: dict[str, list[str]] = {item.value: [] for item in IsolationClass}
        for row in self._by_model.values():
            grouped[row.isolation.value].append(row.table_name)
        for names in grouped.values():
            names.sort()
        return grouped


def infer_isolation(model: type) -> IsolationClass:
    """按 tenant_id 列推断类别。没有该列是全局表，可空是混合表，非空是租户表。"""
    table = getattr(model, "__table__", None)
    if table is None or "tenant_id" not in table.c:
        return IsolationClass.GLOBAL
    if table.c.tenant_id.nullable:
        return IsolationClass.NULLABLE_TENANT
    return IsolationClass.TENANT_SCOPED


def build_registry(base: type, reasons: Mapping[str, str]) -> IsolationRegistry:
    """根据 Declarative Base 上的映射类建立登记表。

    租户表可以不写原因。全局表和混合表必须在 reasons 里用类名说明为什么不能
    一律加上 tenant_id。reasons 里多出来的类名视为笔误并拒绝。
    """
    mappers: Any = getattr(getattr(base, "registry", None), "mappers", None)
    if mappers is None:
        raise RegistryError("base 没有 SQLAlchemy registry")
    registry = IsolationRegistry()
    seen: set[str] = set()
    for mapper in mappers:
        model = mapper.class_
        seen.add(model.__name__)
        isolation = infer_isolation(model)
        reason = reasons.get(model.__name__, "").strip()
        if isolation is not IsolationClass.TENANT_SCOPED and not reason:
            raise RegistryError(f"{model.__name__} 是 {isolation.value}，必须说明原因")
        if isolation is not infer_isolation(model):
            raise RegistryError(f"{model.__name__} 的登记与列定义不一致")
        registry.register(model, isolation, reason=reason)
    unknown = sorted(set(reasons) - seen)
    if unknown:
        raise RegistryError(f"原因列表中的模型不存在: {', '.join(unknown)}")
    registry.freeze()
    return registry
