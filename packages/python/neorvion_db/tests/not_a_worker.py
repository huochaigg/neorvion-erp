"""调用方不在白名单时不能打开特权会话。"""

from neorvion_db import PrivilegedOperation, open_privileged_session


def steal(registry, engine) -> None:
    open_privileged_session(
        PrivilegedOperation.WORKER_CLAIM,
        registry=registry,
        allowed_callers=frozenset({"app.tasks.worker"}),
        bind=engine,
    )
