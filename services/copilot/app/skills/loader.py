from __future__ import annotations

import time
from dataclasses import dataclass, field
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
    resource_metrics: dict[str, dict[str, int | float]] = field(default_factory=dict)


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
        metrics: dict[str, dict[str, int | float]] = {}
        requested = self._requested_resources(task, version)
        for path in requested:
            started = time.perf_counter()
            resources[path] = self.read_resource(version, path)
            content = resources[path]
            metrics[path] = {
                "bytes": len(content.encode("utf-8")),
                "estimated_tokens": max(1, (len(content) + 2) // 3),
                "load_ms": round((time.perf_counter() - started) * 1000, 3),
            }
        context_size = len(version.instructions) + sum(len(item) for item in resources.values())
        if context_size > min(settings.skill_context_max_chars, version.token_budget * 4):
            raise AppError("Skill 上下文超过预算", code=42287, status_code=422)
        return LoadedSkill(
            skill=skill,
            version=version,
            loaded_resources=resources,
            resource_metrics=metrics,
        )

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
    def _requested_resources(task: str, version: SkillVersion) -> list[str]:
        """依据版本化 Metadata 的触发词按需加载，不在运行时代码写死 Skill 名称。"""
        lowered = task.lower()
        configured = version.source_metadata.get("resource_triggers", {})
        frontmatter_metadata = version.source_metadata.get("metadata", {})
        package_triggers = (
            frontmatter_metadata.get("neorvion-resource-triggers", "")
            if isinstance(frontmatter_metadata, dict)
            else ""
        )
        selected: list[str] = []
        for path in sorted(version.resources):
            value = configured.get(path, []) if isinstance(configured, dict) else []
            triggers = (
                [item.strip().lower() for item in value.split(",") if item.strip()]
                if isinstance(value, str)
                else [str(item).strip().lower() for item in value if str(item).strip()]
                if isinstance(value, list)
                else []
            )
            if not triggers and isinstance(package_triggers, str):
                triggers = [item.strip().lower() for item in package_triggers.split(",") if item.strip()]
            basename = PurePosixPath(path).name.lower()
            explicit = path.lower() in lowered or basename in lowered
            if explicit or any(trigger in lowered for trigger in triggers):
                selected.append(path)
            if len(selected) >= settings.skill_resources_max_files:
                break
        return selected
