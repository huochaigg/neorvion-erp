from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.models.ecosystem import Skill, SkillVersion


@dataclass(frozen=True, slots=True)
class SkillCatalogEntry:
    skill_id: int
    version_id: int
    skill_key: str
    name: str
    description: str
    version: int


class SkillCatalog:
    """只查询轻量 Metadata；未选择前不读取 instructions 或 resources。"""

    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context

    async def available(self) -> list[SkillCatalogEntry]:
        if PermissionCode.COPILOT_SKILL_RUN.value not in self.context.permission_codes:
            return []
        rows = (
            await self.session.execute(
                select(
                    Skill.id,
                    SkillVersion.id,
                    Skill.skill_key,
                    Skill.name,
                    Skill.description,
                    SkillVersion.version,
                    SkillVersion.required_permissions,
                )
                .join(
                    SkillVersion,
                    (SkillVersion.tenant_id == Skill.tenant_id)
                    & (SkillVersion.skill_id == Skill.id)
                    & (SkillVersion.version == Skill.current_version),
                )
                .where(
                    Skill.tenant_id == self.context.tenant_id,
                    Skill.enabled.is_(True),
                    Skill.approval_status == "APPROVED",
                    SkillVersion.approval_status == "APPROVED",
                    SkillVersion.risk_level == "READ_ONLY",
                )
                .order_by(Skill.id)
            )
        ).all()
        permissions = self.context.permission_codes
        return [
            SkillCatalogEntry(
                skill_id=row[0],
                version_id=row[1],
                skill_key=row[2],
                name=row[3],
                description=row[4],
                version=row[5],
            )
            for row in rows
            if set(row[6]).issubset(permissions)
        ]
