from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.redis import ping_redis
from app.schemas.health import HealthCheckData


class HealthService:
    """探活 MySQL 与 Redis。任一依赖失败只标记状态，不抛出，避免把探活变成故障点。"""

    def __init__(self, session: Session) -> None:
        self.session = session

    def check(self) -> HealthCheckData:
        return HealthCheckData(
            mysql=self._check_mysql(),
            redis="ok" if ping_redis() else "unavailable",
        )

    def _check_mysql(self) -> str:
        try:
            self.session.execute(text("SELECT 1"))
            return "ok"
        except Exception:
            return "unavailable"
