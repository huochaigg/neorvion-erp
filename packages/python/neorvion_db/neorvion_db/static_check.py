"""Repository 静态检查。只能发现明显漏写 tenant_id 的查询，不能代替运行时守卫。"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

_QUERY_NAMES = {"select", "update", "delete", "text"}
_FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


@dataclass(frozen=True, slots=True)
class AllowedQuery:
    """一处合法的无租户查询。reason 说明它为什么不能加 tenant_id。"""

    qualname: str
    reason: str


@dataclass(frozen=True, slots=True)
class Finding:
    """未登记的危险查询。"""

    qualname: str
    line: int


@dataclass(frozen=True, slots=True)
class ScanReport:
    """静态扫描结果。findings 为空不等于运行时已经隔离。"""

    findings: tuple[Finding, ...]
    stale: tuple[str, ...]
    redundant: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.findings and not self.stale and not self.redundant


def scan_repositories(
    root: Path,
    allowlist: tuple[AllowedQuery, ...] | list[AllowedQuery],
) -> ScanReport:
    """扫描 Repository 目录。

    函数自己写了 Model.tenant_id / ensure_tenant，或直接调用了同文件里这样做的函数，
    视为已有租户标记。只按参数名出现 tenant_id 不算。未覆盖的查询必须登记原因。
    这仍然不能证明运行时一定带上了正确租户。
    """
    reasons = {item.qualname: item.reason.strip() for item in allowlist}
    blank = [name for name, reason in reasons.items() if len(reason) < 8]
    if blank:
        raise ValueError("允许列表的原因过短: " + ", ".join(blank))
    seen: dict[str, _FunctionFact] = {}
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for qualname, node in _functions(tree):
            key = f"{relative}:{qualname}"
            seen[key] = _FunctionFact(
                dangerous=_is_dangerous(node),
                mentions_tenant=_mentions_tenant(node),
                callees=_callees(node),
                line=node.lineno,
            )
    covered = {key: _is_covered(key, seen, set()) for key in seen}
    findings: list[Finding] = []
    redundant: list[str] = []
    for key, fact in seen.items():
        unprotected = fact.dangerous and not covered[key]
        allowed = key in reasons
        if unprotected and not allowed:
            findings.append(Finding(key, fact.line))
        elif allowed and not unprotected:
            redundant.append(key)
    stale = tuple(sorted(set(reasons) - set(seen)))
    return ScanReport(
        findings=tuple(sorted(findings, key=lambda item: item.qualname)),
        stale=stale,
        redundant=tuple(sorted(redundant)),
    )


@dataclass(frozen=True, slots=True)
class _FunctionFact:
    dangerous: bool
    mentions_tenant: bool
    callees: frozenset[str]
    line: int


def _is_covered(key: str, seen: dict[str, _FunctionFact], stack: set[str]) -> bool:
    """自己带租户标记，或直接调用的同文件函数带租户标记。"""
    fact = seen[key]
    if fact.mentions_tenant:
        return True
    if key in stack:
        return False
    stack.add(key)
    try:
        for callee in fact.callees:
            for candidate in _callee_keys(key, callee):
                if candidate in seen and _is_covered(candidate, seen, stack):
                    return True
    finally:
        stack.remove(key)
    return False


def _callee_keys(key: str, callee: str) -> tuple[str, ...]:
    file_name, qualname = key.split(":", 1)
    keys = [f"{file_name}:{callee}"]
    if "." in qualname:
        owner = qualname.rsplit(".", 1)[0]
        keys.append(f"{file_name}:{owner}.{callee}")
    return tuple(keys)


def _callees(fn: ast.AST) -> frozenset[str]:
    names: set[str] = set()
    for node in _local_nodes(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id == "self"
        ):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return frozenset(names)


def _functions(tree: ast.AST, prefix: str = "") -> list[tuple[str, ast.AST]]:
    found: list[tuple[str, ast.AST]] = []
    body = getattr(tree, "body", [])
    for node in body:
        if isinstance(node, ast.ClassDef):
            name = f"{prefix}{node.name}"
            found.extend(_functions(node, prefix=f"{name}."))
        elif isinstance(node, _FUNCTION_TYPES):
            found.append((f"{prefix}{node.name}", node))
            found.extend(_functions(node, prefix=f"{prefix}{node.name}."))
    return found


def _local_nodes(node: ast.AST):
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.ClassDef, *_FUNCTION_TYPES)):
            continue
        yield child
        yield from _local_nodes(child)


def _mentions_tenant(fn: ast.AST) -> bool:
    """只认 Model.tenant_id 和 ensure_tenant。参数名碰巧叫 tenant_id 不算过滤。"""
    for node in _local_nodes(fn):
        if isinstance(node, ast.Name) and node.id == "ensure_tenant":
            return True
        if isinstance(node, ast.Attribute) and node.attr in {"tenant_id", "ensure_tenant"}:
            return True
    return False


def _is_dangerous(fn: ast.AST) -> bool:
    for node in _local_nodes(fn):
        if isinstance(node, ast.Call) and _is_query_call(node):
            return True
    return False


_SESSION_CALLS = {"get", "execute", "scalars", "scalar", "scalar_one", "scalar_one_or_none"}


def _is_query_call(node: ast.Call) -> bool:
    """select/update/delete/text，以及 session.get / execute / scalars。

    dict.get 和普通对象的 execute 不计入。session.execute(stmt) 即使语句在别处构造，
    也视为一次查询；同函数或直接调用的同文件函数若写了 tenant_id，则视为已覆盖。
    """
    func = node.func
    if isinstance(func, ast.Name) and func.id in _QUERY_NAMES:
        return True
    if isinstance(func, ast.Attribute) and func.attr in _SESSION_CALLS:
        owner = func.value
        if isinstance(owner, ast.Name) and owner.id in {"session", "db"}:
            return True
        if isinstance(owner, ast.Attribute) and owner.attr == "session":
            return True
    return False
