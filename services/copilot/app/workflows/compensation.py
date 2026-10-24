from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CompensationSpec:
    step_type: str
    action: str | None
    automatic: bool
    reason: str


class CompensationRegistry:
    """只登记有真实安全语义的补偿；V7 不把删除或反向调拨伪装成回滚。"""

    def for_step(self, step_type: str) -> CompensationSpec:
        if step_type in {"ERP_READ", "KNOWLEDGE_READ", "DETERMINISTIC_ANALYSIS", "PROPOSAL"}:
            return CompensationSpec(
                step_type, None, True, "步骤无 ERP 业务副作用，可安全重试或停止"
            )
        return CompensationSpec(
            step_type, None, False, "已创建 ERP 单据没有通用安全逆操作，需要人工处理"
        )


compensation_registry = CompensationRegistry()
