from typing import Literal

from pydantic import BaseModel


class HealthCheckData(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["copilot"] = "copilot"
    version: str
    git_sha: str
    identity: Literal["ok", "unavailable"]


class ModelStatusData(BaseModel):
    state: Literal["available", "mock", "unconfigured", "unavailable"]
    provider: str
    model: str | None
    detail: str | None

