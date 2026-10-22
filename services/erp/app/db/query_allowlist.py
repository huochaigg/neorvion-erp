"""ERP 中不能从函数体看出 tenant_id 的查询。静态登记不能代替运行时隔离。"""

from neorvion_db import AllowedQuery

ALLOWLIST = (
    AllowedQuery(
        "system_jobs.py:lock_task_for_worker",
        "Worker 按全局 task_id 领取排队任务，随后用任务行上的 tenant_id 进入业务",
    ),
    AllowedQuery(
        "inventory.py:InventoryRepository._execute_update",
        "只执行调用方已经写好 tenant_id 的 Core UPDATE，本函数不追加条件",
    ),
    AllowedQuery(
        "outbound.py:OutboundOrderRepository._pick_stmt",
        "只构造拣货 select，调用方 list_picks 再追加 OutboundPick.tenant_id",
    ),
    AllowedQuery(
        "system_jobs.py:claim_pending_events",
        "Outbox 按全局队列领取待处理事件，事件行自己带可空 tenant_id",
    ),
)
