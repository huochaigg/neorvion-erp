from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.health import HealthCheckData
from app.services.identity import identity_client


class HealthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def check(self) -> HealthCheckData:
        postgres: str = "ok"
        pgvector: str = "not_installed"
        try:
            await self.session.execute(text("SELECT 1"))
        except Exception:
            postgres = "unavailable"
            pgvector = "unavailable"
        else:
            try:
                result = await self.session.scalar(
                    text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                )
                pgvector = "ok" if result else "not_installed"
            except Exception:
                pgvector = "unavailable"

        identity = "ok" if await identity_client.ping() else "unavailable"
        return HealthCheckData(
            postgres=postgres,  # type: ignore[arg-type]
            pgvector=pgvector,  # type: ignore[arg-type]
            identity=identity,  # type: ignore[arg-type]
            milestone="Knowledge V2",
            version=settings.app_version,
            git_sha=settings.git_sha,
        )
