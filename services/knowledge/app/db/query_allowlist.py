"""Knowledge 中 Worker 与平台资源查询的登记。静态检查不能代替运行时隔离。"""

from neorvion_db import AllowedQuery

ALLOWLIST = (
    AllowedQuery(
        "system_queue.py:list_queued_tasks",
        "Worker 扫描全部排队文档任务，业务处理阶段再绑定租户",
    ),
    AllowedQuery(
        "system_queue.py:fail_stale_tasks",
        "Worker 启动时回收全部僵死任务，不按单一租户过滤",
    ),
    AllowedQuery(
        "system_queue.py:list_queued_runs",
        "Worker 扫描全部排队评测，执行前再读取运行行上的租户",
    ),
    AllowedQuery(
        "system_queue.py:pause_stale_runs",
        "Worker 回收全部过期评测租约，不能只看当前请求租户",
    ),
    AllowedQuery(
        "ops.py:ApiKeyRepository.get_by_hash",
        "API Key 认证先按全局哈希定位密钥，再校验请求头与密钥租户一致",
    ),
    AllowedQuery(
        "rag.py:ModelProfileRepository.list_all",
        "平台模型配置没有 tenant_id，供各租户选择",
    ),
    AllowedQuery(
        "rag.py:ModelProfileRepository.get",
        "按主键读取平台模型配置，该表没有 tenant_id",
    ),
)
