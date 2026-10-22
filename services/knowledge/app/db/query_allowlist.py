"""Knowledge 中 Worker 与平台资源查询的登记。静态检查不能代替运行时隔离。"""

from neorvion_db import AllowedQuery

ALLOWLIST = (
    AllowedQuery(
        "documents.py:TaskRepository.get_by_id",
        "Worker 按全局任务主键领取，随后用任务行上的 tenant_id 处理文档",
    ),
    AllowedQuery(
        "documents.py:TaskRepository.list_queued",
        "Worker 扫描全部排队文档任务，业务处理阶段再绑定租户",
    ),
    AllowedQuery(
        "documents.py:TaskRepository.fail_stale_running",
        "Worker 启动时回收全部僵死任务，不按单一租户过滤",
    ),
    AllowedQuery(
        "evaluation.py:EvaluationRepository.get_run_for_update",
        "按评测运行主键加锁，当前无调用方，登记以免接入普通接口",
    ),
    AllowedQuery(
        "evaluation.py:EvaluationRepository.list_queued_runs",
        "Worker 扫描全部排队评测，执行前再读取运行行上的租户",
    ),
    AllowedQuery(
        "evaluation.py:EvaluationRepository.pause_stale_running",
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
