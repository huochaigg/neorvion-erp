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
    milestone: str = Field(default="V16", description="当前 ERP Core 里程碑")
    version: str = Field(default="1.0.0", description="应用版本号，不含密钥")
    git_sha: str = Field(default="", description="构建时的 Git commit SHA，不含密钥")
