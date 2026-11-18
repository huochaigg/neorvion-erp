from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.models.ecosystem import Skill, SkillVersion
from app.skills.catalog import SkillCatalogEntry


@dataclass(frozen=True, slots=True)
class LoadedSkill:
    skill: Skill
    version: SkillVersion
    loaded_resources: dict[str, str]


class SkillRuntimeLoader:
    """只从已审核数据库快照加载选中版本，磁盘变更不会直接进入运行时。"""

    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context

    async def load(self, entry: SkillCatalogEntry, task: str) -> LoadedSkill:
        row = (
            await self.session.execute(
                select(Skill, SkillVersion)
                .join(
                    SkillVersion,
                    (SkillVersion.tenant_id == Skill.tenant_id)
                    & (SkillVersion.skill_id == Skill.id),
                )
                .where(
                    Skill.tenant_id == self.context.tenant_id,
                    Skill.id == entry.skill_id,
                    SkillVersion.id == entry.version_id,
                    SkillVersion.version == Skill.current_version,
                    Skill.enabled.is_(True),
                    Skill.approval_status == "APPROVED",
                    SkillVersion.approval_status == "APPROVED",
                    SkillVersion.risk_level == "READ_ONLY",
                )
            )
        ).first()
        if row is None:
            raise AppError("选中的 Skill 版本不可用", code=40483, status_code=404)
        skill, version = row
        if not set(version.required_permissions).issubset(self.context.permission_codes):
            raise AppError("无权加载该 Skill", code=40385, status_code=403)
        resources: dict[str, str] = {}
        requested = self._requested_resources(skill.skill_key, task, version.resources)
        for path in requested:
            resources[path] = self.read_resource(version, path)
        context_size = len(version.instructions) + sum(len(item) for item in resources.values())
        if context_size > min(settings.skill_context_max_chars, version.token_budget * 4):
            raise AppError("Skill 上下文超过预算", code=42287, status_code=422)
        return LoadedSkill(skill=skill, version=version, loaded_resources=resources)

    @staticmethod
    def read_resource(version: SkillVersion, path: str) -> str:
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or len(pure.parts) != 2 or pure.parts[0] != "references":
            raise AppError("Skill Reference 路径非法", code=40387, status_code=403)
        value = version.resources.get(pure.as_posix())
        if value is None:
            raise AppError("Skill Reference 不存在", code=40487, status_code=404)
        if len(value.encode("utf-8")) > settings.skill_reference_max_bytes:
            raise AppError("Skill Reference 超过运行时限制", code=42287, status_code=422)
        return value

    @staticmethod
    def _requested_resources(skill_key: str, task: str, resources: dict[str, str]) -> list[str]:
        lowered = task.lower()
        needs_rules = {
            "inventory-analysis": ("风险", "risk"),
            "sales-order-review": ("审查", "风险", "review", "audit"),
            "knowledge-research": ("引用", "来源", "依据", "citation", "source"),
        }
        if any(marker in lowered for marker in needs_rules.get(skill_key, ())):
            return list(sorted(resources))[: settings.skill_resources_max_files]
        return []
