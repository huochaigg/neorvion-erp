"""核对一个服务的模型登记、特权暴露面和 Repository 静态检查。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from neorvion_db.errors import PrivilegeError
from neorvion_db.privileges import PrivilegedOperation
from neorvion_db.sessions import open_privileged_session
from neorvion_db.static_check import scan_repositories


def main(argv: list[str] | None = None) -> int:
    """导入服务的 app.db.isolation 并打印登记摘要。失败时返回 1。"""
    parser = argparse.ArgumentParser(description="检查服务的租户隔离登记")
    parser.add_argument("service_root", type=Path)
    args = parser.parse_args(argv)
    root = args.service_root.resolve()
    sys.path.insert(0, str(root))
    from app.db.isolation import REGISTRY
    from app.db.query_allowlist import ALLOWLIST
    from app.db.system_access import PRIVILEGED_CALLERS

    print(f"service={root.name}")
    for kind, tables in REGISTRY.summary().items():
        print(f"{kind}={len(tables)}")
        for table in tables:
            print(f"  {kind}:{table}")
    report = scan_repositories(root / "app" / "repositories", ALLOWLIST)
    if not report.ok:
        for item in report.findings:
            print(f"finding:{item.qualname}:{item.line}")
        for item in report.stale:
            print(f"stale:{item}")
        for item in report.redundant:
            print(f"redundant:{item}")
        return 1
    for operation, callers in PRIVILEGED_CALLERS.items():
        if not isinstance(operation, PrivilegedOperation):
            print("privileged caller key must be PrivilegedOperation")
            return 1
        try:
            open_privileged_session(operation, registry=REGISTRY, allowed_callers=callers)
        except PrivilegeError:
            continue
        print(f"checker must not open {operation.value}")
        return 1
    print("static=ok")
    print("privilege_exposure=ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
