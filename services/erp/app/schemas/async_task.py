from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AsyncTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str = Field(..., description="异步任务对外唯一标识，与数据库自增 id 分离")
    task_type: str
    status: str
    progress: int = Field(..., description="异步任务当前进度百分比，范围 0-100")
    title: str
    description: str | None = None
    payload: dict[str, Any] | None = None
    result: dict[str, Any] | None = Field(None, description="成功结果摘要，不含服务器任意路径")
    error_message: str | None = Field(None, description="可展示的简要失败原因")
    retry_count: int
    max_retries: int
    created_by: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    queued: bool | None = Field(
        default=None,
        description="本次创建是否已成功进入 Redis 队列；false 表示仍为 PENDING，可重试入队",
    )


class AsyncTaskListOut(BaseModel):
    items: list[AsyncTaskOut]
    total: int
    page: int
    page_size: int


class AsyncTaskLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: str
    level: str
    message: str
    created_at: datetime


class ReportExportCreate(BaseModel):
    kind: str = Field(..., description="sales_trend / purchase_trend / low_stock")
    start_date: str | None = None
    end_date: str | None = None
    warehouse_id: int | None = None
    low_stock_threshold: int | None = None
