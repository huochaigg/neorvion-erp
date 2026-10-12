from typing import Literal

from pydantic import BaseModel, Field


class HealthCheckData(BaseModel):
    app: Literal["ok"] = "ok"
    mysql: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]
    worker: Literal["ok", "unavailable"] = Field(
        default="unavailable",
        description="独立 Worker 心跳。Redis 中 erp:worker:heartbeat 未过期则为 ok",
    )
    milestone: str = Field(default="V15", description="当前 ERP Core 里程碑")
