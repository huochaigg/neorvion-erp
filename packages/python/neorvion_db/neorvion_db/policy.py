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
from neorvion_db.privileges import (
    PRIVILEGED_OPERATION_KEY,
    REVIEWED_SQL_KEY,
    PrivilegedOperation,
    ReviewedSql,
)
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


def _reviewed_utility(execute_state: Any) -> bool:
    """只放行带 ReviewedSql 枚举、且 SQL 本身是咨询锁的语句。

    不根据 SQL 里有没有 tenant_id 这几个字符判断安全。枚举和语句文本必须同时符合。
    """
    kind = execute_state.execution_options.get(REVIEWED_SQL_KEY)
    if kind is not ReviewedSql.ADVISORY_LOCK:
        return False
    text_sql = " ".join(str(execute_state.statement).split()).upper()
    if "TENANT_ID" in text_sql or "FROM " in text_sql:
        return False
    return text_sql.startswith("SELECT GET_LOCK(") or text_sql.startswith("SELECT RELEASE_LOCK(")


def _bound_int(expr: Any) -> int | None:
    """取出绑定参数或字面量里的整数。布尔值不算。无法静态确定的值返回 None。"""
    if type(expr) is int:
        return expr
    if getattr(expr, "callable", None) is not None:
        return None
    for attr in ("effective_value", "value"):
        value = getattr(expr, attr, None)
        if type(value) is int:
            return value
    return None


def _is_tenant_column(expr: Any, model: type) -> bool:
    """判断表达式是不是该模型的 tenant_id 列。不看 SQL 字符串。"""
    key = getattr(expr, "key", None) or getattr(expr, "name", None)
    if key != "tenant_id":
        return False
    parent = getattr(expr, "class_", None)
    if parent is model:
        return True
    table = getattr(expr, "table", None)
    return getattr(table, "name", None) == getattr(model, "__tablename__", None)


def _eq_binds_tenant(expr: Any, model: type, tenant_id: int) -> bool:
    from sqlalchemy.sql import operators
    from sqlalchemy.sql.elements import BinaryExpression

    if not isinstance(expr, BinaryExpression) or expr.operator is not operators.eq:
        return False
    pairs = ((expr.left, expr.right), (expr.right, expr.left))
    return any(
        _is_tenant_column(column, model) and _bound_int(value) == tenant_id
        for column, value in pairs
    )


def _predicate_binds_tenant(clause: Any, model: type, tenant_id: int) -> bool:
    """AND 中任一分支能证明即可。OR 必须每一支都能证明，否则另一支可以命中别的租户。"""
    from sqlalchemy.sql import operators
    from sqlalchemy.sql.elements import BooleanClauseList, Grouping

    if clause is None:
        return False
    if isinstance(clause, Grouping):
        return _predicate_binds_tenant(clause.element, model, tenant_id)
    if isinstance(clause, BooleanClauseList):
        parts = list(clause.clauses)
        if not parts:
            return False
        if clause.operator is operators.and_:
            return any(_predicate_binds_tenant(part, model, tenant_id) for part in parts)
        if clause.operator is operators.or_:
            return all(_predicate_binds_tenant(part, model, tenant_id) for part in parts)
        return False
    return _eq_binds_tenant(clause, model, tenant_id)


def _direct_table_names(statement: Any) -> set[str]:
    """只看本层 FROM 里的表。子查询留给内层 SELECT 自己证明，避免外层 WHERE 把表再拉进来。"""
    names: set[str] = set()
    if not hasattr(statement, "get_final_froms"):
        return names
    for clause in statement.get_final_froms():
        for table in _direct_tables(clause):
            if isinstance(getattr(table, "name", None), str):
                names.add(table.name)
    return names


def _direct_tables(clause: Any) -> list[Any]:
    if clause is None:
        return []
    left = getattr(clause, "left", None)
    right = getattr(clause, "right", None)
    if left is not None and right is not None:
        return [*_direct_tables(left), *_direct_tables(right)]
    element = getattr(clause, "element", None)
    if element is not None and element is not clause and hasattr(element, "get_final_froms"):
        return []
    if hasattr(clause, "c") and isinstance(getattr(clause, "name", None), str):
        return [clause]
    return []


def _limit_nested_selects(statement: Any, registry: IsolationRegistry, tenant_id: int) -> Any:
    """给子查询里已经出现的租户表补上当前租户条件。

    列表页常用 ``count().select_from(stmt.subquery())``。内层 JOIN 了客户、仓库等表，
    手写条件往往只写在主表上。这里沿用 SELECT 的后盾：不删原条件，只对子查询 FROM 里
    已经连接的租户表再加等值。无法改写的语句不会静默执行。
    """
    from sqlalchemy.sql import visitors

    by_table = {row.table_name: row for row in registry.registrations()}

    def _visit_select(element: Any) -> None:
        pending = []
        for name in _direct_table_names(element):
            row = by_table.get(name)
            if row is None or row.isolation is IsolationClass.GLOBAL:
                continue
            if _predicate_binds_tenant(element.whereclause, row.model, tenant_id):
                continue
            pending.append(row.model.tenant_id == tenant_id)
        if not pending:
            return
        element._where_criteria += tuple(pending)

    return visitors.cloned_traverse(statement, {}, {"select": _visit_select})


def _require_write_predicate(
    statement: Any,
    classified: list[tuple[type, IsolationClass]],
    tenant_id: int,
) -> None:
    """UPDATE/DELETE 必须自己写出 tenant_id = 当前会话。缺少或值不一致都拒绝。"""
    where = getattr(statement, "whereclause", None)
    for model, isolation in classified:
        if isolation is IsolationClass.GLOBAL:
            continue
        if not _predicate_binds_tenant(where, model, tenant_id):
            raise TenantIsolationError(
                f"{model.__name__} 的 UPDATE/DELETE 缺少与会话租户 "
                f"{tenant_id} 一致的 tenant_id 条件"
            )


def _core_dml_proven(execute_state: Any, tenant_id: int, registry: IsolationRegistry) -> bool:
    """Core DML 能按表名回到登记、且 WHERE 或 INSERT 值能证明租户时才放行。"""
    statement = execute_state.statement
    if not getattr(statement, "is_dml", False):
        return False
    table = getattr(statement, "table", None)
    name = getattr(table, "name", None)
    model = next(
        (row.model for row in registry.registrations() if row.table_name == name),
        None,
    )
    if model is None:
        return False
    isolation = registry.require(model).isolation
    classified = [(model, isolation)]
    if getattr(statement, "is_insert", False):
        _assert_insert_tenant(execute_state, tenant_id, classified)
        return True
    if isolation is IsolationClass.GLOBAL:
        return True
    return _predicate_binds_tenant(getattr(statement, "whereclause", None), model, tenant_id)


def guard_tenant_execute(execute_state: Any) -> None:
    """租户会话的 do_orm_execute。

    SELECT 用 with_loader_criteria 和 WHERE 追加当前租户，保留调用方原来的条件。
    聚合 count() 的结果列不是实体，所以不能只依赖 loader criteria。
    UPDATE/DELETE 不自动补条件：WHERE 里必须有与会话一致的 tenant_id 等值。
    比较的是 SQLAlchemy 子句结构，不是 SQL 字符串里有没有 tenant_id。
    text()、无法证明的 Core DML 直接拒绝。Connection.execute 不进入本事件。
    """
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    tenant_id = execute_state.session.tenant_id
    registry = _registry_of(execute_state.session)
    if not execute_state.is_orm_statement:
        if _reviewed_utility(execute_state) or _core_dml_proven(execute_state, tenant_id, registry):
            return
        raise TenantIsolationError(
            "租户会话拒绝 text() 和无法证明租户条件的 Core SQL"
        )
    models = _models_in_statement(execute_state, registry)
    classified = _classifications(registry, models)
    if execute_state.is_insert:
        _assert_insert_tenant(execute_state, tenant_id, classified)
        return
    if not classified and not execute_state.is_select:
        raise TenantIsolationError("无法判断语句涉及的模型，租户会话拒绝执行")
    if execute_state.is_select:
        execute_state.statement = _limit_nested_selects(
            execute_state.statement, registry, tenant_id
        )
        if not classified and not _direct_table_names(execute_state.statement):
            return
        if not classified:
            raise TenantIsolationError("无法判断语句涉及的模型，租户会话拒绝执行")
    if execute_state.is_update or execute_state.is_delete:
        _require_write_predicate(execute_state.statement, classified, tenant_id)
    direct_tables = _direct_table_names(execute_state.statement)
    statement = execute_state.statement
    for model, isolation in classified:
        if isolation is IsolationClass.GLOBAL:
            continue
        if execute_state.is_select and model.__tablename__ in direct_tables:
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
    """特权会话默认什么都不放行。查询必须带上与会话相同的枚举操作。

    flush 产生的 INSERT/UPDATE/DELETE 没有地方挂 execution_options。
    这些语句只在 Session._flushing 期间放行，before_flush 仍检查租户改绑。
    """
    if execute_state.is_column_load or execute_state.is_relationship_load:
        return
    flushing = bool(getattr(execute_state.session, "_flushing", False))
    if flushing and (
        execute_state.is_insert or execute_state.is_update or execute_state.is_delete
    ):
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
