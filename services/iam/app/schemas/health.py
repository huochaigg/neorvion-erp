from typing import Literal

from pydantic import BaseModel, Field


class HealthCheckData(BaseModel):
    app: Literal["ok"] = "ok"
    mysql: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]
    worker: Literal["ok", "unavailable"] = "unavailable"
    milestone: str = Field(default="IAM-V2", description="当前 IAM 里程碑")
    version: str = Field(default="2.0.0")
    git_sha: str = Field(default="")
