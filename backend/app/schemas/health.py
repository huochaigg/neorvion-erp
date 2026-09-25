from typing import Literal

from pydantic import BaseModel, Field


class HealthCheckData(BaseModel):
    app: Literal["ok"] = "ok"
    mysql: Literal["ok", "unavailable"]
    redis: Literal["ok", "unavailable"]
    milestone: str = Field(default="V2.1.1")
