from typing import Literal

from pydantic import BaseModel, Field


class HealthCheckData(BaseModel):
    app: Literal["ok"] = "ok"
    postgres: Literal["ok", "unavailable"]
    pgvector: Literal["ok", "unavailable", "not_installed"] = Field(
        description="V3 检索依赖 pgvector；未安装时标记 not_installed",
    )
    identity: Literal["ok", "unavailable"] = Field(
        description="ERP 身份内省可达性；失败不把 Knowledge 标为整体 down",
    )
    milestone: str = Field(default="Knowledge V4", description="当前 Knowledge 里程碑")
    version: str = Field(default="4.0.0", description="应用版本号，不含密钥")
    git_sha: str = Field(default="", description="构建时的 Git commit SHA，不含密钥")
