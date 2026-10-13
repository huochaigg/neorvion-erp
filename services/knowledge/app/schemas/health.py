from typing import Literal

from pydantic import BaseModel, Field


class HealthCheckData(BaseModel):
    app: Literal["ok"] = "ok"
    postgres: Literal["ok", "unavailable"]
    pgvector: Literal["ok", "unavailable", "not_installed"] = Field(
        description="V2 不依赖向量检索；未安装时标记 not_installed，不阻塞启动",
    )
    identity: Literal["ok", "unavailable"] = Field(
        description="ERP 身份内省可达性；失败不把 Knowledge 标为整体 down",
    )
    milestone: str = Field(default="Knowledge V2", description="当前 Knowledge 里程碑")
    version: str = Field(default="2.0.0", description="应用版本号，不含密钥")
    git_sha: str = Field(default="", description="构建时的 Git commit SHA，不含密钥")
