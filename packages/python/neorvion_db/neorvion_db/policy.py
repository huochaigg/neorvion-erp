"""ORM 执行与 flush 守卫。只由三类会话子类调用，不监听普通 Session。"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import with_loader_criteria

from neorvion_db.errors import (
    PrivilegeError,
    RegistryError,
    TenantIsolationError,
    TenantRebindError,
)
from neorvion_db.privileges import PRIVILEGED_OPERATION_KEY, PrivilegedOperation
from neorvion_db.registry import IsolationClass, IsolationRegistry


def _registry_of(session: Any) -> IsolationRegistry:
    registry = getattr(session, "registry", None)
    if not isinstance(registry, IsolationRegistry) or not registry.frozen:
        raise RegistryError("会话缺少已冻结的隔离登记表")
    return registry


def _models_in_statement(execute_state: Any, registry: IsolationRegistry) -> list[type]:
    """合并结果列中的实体和 FROM 子句里的表。

    all_mappers 只包含会出现在结果列里的实体。聚合 count() 只 select_from
    一张表时，结果列没有实体，必须再按表名回到登记表。
    """
    models = _mapped_models(execute_state)
    by_table = {row.table_name: row.model for row in registry.registrations()}
    statement = execute_state.statement
    if not hasattr(statement, "get_final_froms"):
        return models
    for clause in statement.get_final_froms():
        for table in _leaf_tables(clause):
            model = by_table.get(table.name)
            if model is None:
                raise TenantIsolationError(f"语句包含未登记的表 {table.name}")
            if model not in models:
                models.append(model)
    return models


def _leaf_tables(clause: Any) -> list[Any]:
    """把 JOIN 拆到最终的 Table。别名再往下取 element。"""
    if clause is None:
        return []
    left = getattr(clause, "left", None)
    right = getattr(clause, "right", None)
    if left is not None and right is not None:
        return [*_leaf_tables(left), *_leaf_tables(right)]
    element = getattr(clause, "element", None)
    if element is not None and element is not clause:
        return _leaf_tables(element)
    if hasattr(clause, "c") and isinstance(getattr(clause, "name", None), str):
        return [clause]
    return []


def _mapped_models(execute_state: Any) -> list[type]:
    models: list[type] = []
    for mapper in execute_state.all_mappers:
        model = mapper.class_
        if model not in models:
            models.append(model)
    return models


def _classifications(
    registry: IsolationRegistry,
    models: Iterable[type],
) -> list[tuple[type, IsolationClass]]:
    found: list[tuple[type, IsolationClass]] = []
    for model in models:
        found.append((model, registry.require(model).isolation))
    return found


def _tenant_clause(tenant_id: int):
    """生成追加到 ORM 语句上的租户条件。闭包只捕获这一个整数。"""

    def _clause(cls: type):
        return cls.tenant_id == tenant_id

    return _clause


def guard_tenant_execute(execute_state: Any) -> None:
    """租户会话的 do_orm_execute。

    结果列里的 ORM 实体用 with_loader_criteria 追加租户条件。SQLAlchemy 2.0 起，
    该选项对 ORM-enabled UPDATE/DELETE 同样生效。
    select(func.count()).select_from(Model) 的结果列不是实体，loader criteria
    看不到它，所以再按 FROM 里的表显式追加 WHERE。
    text()、Core Table DML 直接拒绝。Connection.execute 不进入本事件。
    """
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    tenant_id = execute_state.session.tenant_id
    registry = _registry_of(execute_state.session)
    if not execute_state.is_orm_statement:
        raise TenantIsolationError(
            "租户会话拒绝 text() 和非 ORM 语句。with_loader_criteria 覆盖不了这些 SQL"
        )
    models = _models_in_statement(execute_state, registry)
    classified = _classifications(registry, models)
    if execute_state.is_insert:
        _assert_insert_tenant(execute_state, tenant_id, classified)
        return
    if not classified:
        raise TenantIsolationError("无法判断语句涉及的模型，租户会话拒绝执行")
    statement = execute_state.statement
    for model, isolation in classified:
        if isolation is IsolationClass.GLOBAL:
            continue
        statement = statement.where(model.tenant_id == tenant_id)
        statement = statement.options(
            with_loader_criteria(
                model,
                _tenant_clause(tenant_id),
                include_aliases=True,
            )
        )
    execute_state.statement = statement


def guard_global_execute(execute_state: Any) -> None:
    """全局身份会话只能碰到登记为 global 的模型。"""
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    registry = _registry_of(execute_state.session)
    if not execute_state.is_orm_statement:
        raise TenantIsolationError("全局身份会话拒绝 text() 和非 ORM 语句")
    for _model, isolation in _classifications(registry, _mapped_models(execute_state)):
        if isolation is not IsolationClass.GLOBAL:
            raise TenantIsolationError("全局身份会话不能读写租户表或混合表")


def guard_privileged_execute(execute_state: Any) -> None:
    """特权会话默认什么都不放行。语句必须带上与会话相同的枚举操作。"""
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    if not execute_state.is_orm_statement:
        raise TenantIsolationError("特权会话拒绝 text()。Connection.execute 同样不受本守卫保护")
    operation = _matching_operation(execute_state)
    if operation is None:
        raise PrivilegeError("特权会话上的语句必须显式声明 PrivilegedOperation，字符串无效")
    _classifications(_registry_of(execute_state.session), _mapped_models(execute_state))


def guard_tenant_flush(session: Any, _flush_context: Any, _instances: Any) -> None:
    """租户会话 flush：租户列必须等于会话租户，禁止改绑，禁止带入其他租户的关联对象。"""
    registry = _registry_of(session)
    tenant_id = session.tenant_id
    for obj in _flush_objects(session):
        _check_tenant_write(session, obj, registry, tenant_id)


def guard_global_flush(session: Any, _flush_context: Any, _instances: Any) -> None:
    """全局身份会话不能 flush 租户对象。"""
    registry = _registry_of(session)
    for obj in _flush_objects(session):
        isolation = registry.require(type(obj)).isolation
        if isolation is not IsolationClass.GLOBAL:
            raise TenantIsolationError("全局身份会话不能写入租户表或混合表")


def guard_privileged_flush(session: Any, _flush_context: Any, _instances: Any) -> None:
    """特权 flush 可以写多个租户的行，但不能把已有行的 tenant_id 改成另一家。"""
    registry = _registry_of(session)
    for obj in _flush_objects(session):
        registration = registry.require(type(obj))
        if registration.isolation is IsolationClass.GLOBAL:
            continue
        state = sa_inspect(obj)
        current = getattr(obj, "tenant_id", None)
        _reject_tenant_rebind(state)
        if registration.isolation is IsolationClass.TENANT_SCOPED and type(current) is not int:
            raise TenantIsolationError("特权会话插入租户行时必须显式写出 tenant_id，不会自动填充")


def _matching_operation(execute_state: Any) -> PrivilegedOperation | None:
    raw = execute_state.execution_options.get(PRIVILEGED_OPERATION_KEY)
    expected = execute_state.session.operation
    if raw is expected and isinstance(raw, PrivilegedOperation):
        return raw
    return None


def _assert_insert_tenant(
    execute_state: Any,
    tenant_id: int,
    classified: list[tuple[type, IsolationClass]],
) -> None:
    """Core INSERT 不进入 before_flush，这里核对参数里的 tenant_id。"""
    needs_tenant = [
        model for model, isolation in classified if isolation is not IsolationClass.GLOBAL
    ]
    if not needs_tenant:
        return
    rows = _insert_rows(execute_state)
    if not rows:
        raise TenantIsolationError("无法确认 INSERT 的 tenant_id，租户会话拒绝执行")
    for row in rows:
        value = row.get("tenant_id")
        if value != tenant_id:
            raise TenantIsolationError("INSERT 的 tenant_id 与会话租户不一致")


def _insert_rows(execute_state: Any) -> list[dict[str, Any]]:
    params = execute_state.parameters
    rows: list[dict[str, Any]] = []
    if isinstance(params, dict) and params:
        rows.append(params)
    elif isinstance(params, list | tuple):
        rows.extend(item for item in params if isinstance(item, dict))
    statement = execute_state.statement
    compiled = getattr(statement, "_values", None)
    if isinstance(compiled, dict) and compiled:
        baked: dict[str, Any] = {}
        for key, value in compiled.items():
            name = getattr(key, "key", None) or getattr(key, "name", None)
            if not isinstance(name, str):
                continue
            raw = getattr(value, "value", value)
            baked[name] = raw
        if baked:
            rows.append(baked)
    return rows


def _flush_objects(session: Any) -> list[object]:
    return [*session.new, *session.dirty, *session.deleted]


def _check_tenant_write(
    session: Any,
    obj: object,
    registry: IsolationRegistry,
    tenant_id: int,
) -> None:
    registration = registry.require(type(obj))
    if registration.isolation is IsolationClass.GLOBAL:
        return
    state = sa_inspect(obj)
    _reject_tenant_rebind(state)
    current = getattr(obj, "tenant_id", None)
    if current != tenant_id:
        raise TenantIsolationError(
            f"{type(obj).__name__}.tenant_id 必须等于会话租户 {tenant_id}，不会自动填充"
        )
    _reject_foreign_relation(obj, state)


def _reject_tenant_rebind(state: Any) -> None:
    if "tenant_id" not in state.mapper.columns:
        return
    history = state.attrs.tenant_id.history
    if history.deleted and history.added and history.deleted[0] != history.added[0]:
        raise TenantRebindError("不能在持久化时把行改到另一个租户")


def _reject_foreign_relation(obj: object, state: Any) -> None:
    """只检查已经加载进内存的关联，避免 flush 时触发懒加载。"""
    own_tenant = getattr(obj, "tenant_id", None)
    for relation in state.mapper.relationships:
        if relation.key not in state.dict:
            continue
        value = state.dict[relation.key]
        related_items = list(value) if relation.uselist else [value]
        for item in related_items:
            if item is None:
                continue
            item_state = sa_inspect(item)
            if "tenant_id" not in item_state.mapper.columns:
                continue
            if getattr(item, "tenant_id", None) != own_tenant:
                raise TenantIsolationError(
                    f"{type(obj).__name__} 不能关联其他租户的 {type(item).__name__}"
                )
