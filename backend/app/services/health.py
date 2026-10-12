from typing import Literal

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.async_tasks import WORKER_HEARTBEAT_KEY
from app.core.redis import ping_redis, redis_client
from app.schemas.health import HealthCheckData

HealthStatus = Literal["ok", "unavailable"]


class HealthService:
    """探活 MySQL、Redis 与 Worker 心跳。任一依赖失败只标记状态，不抛出。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def check(self) -> HealthCheckData:
        redis_ok = ping_redis()
        return HealthCheckData(
            mysql=self._check_mysql(),
            redis="ok" if redis_ok else "unavailable",
            worker=self._check_worker() if redis_ok else "unavailable",
        )

    def _check_worker(self) -> HealthStatus:
        try:
            return "ok" if redis_client.get(WORKER_HEARTBEAT_KEY) else "unavailable"
        except Exception:
            return "unavailable"

    def _check_mysql(self) -> HealthStatus:
        try:
            self.session.execute(text("SELECT 1"))
            return "ok"
        except Exception:
            return "unavailable"
