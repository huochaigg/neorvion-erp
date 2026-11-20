from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

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
    metadata: dict[str, Any] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()
    category: str = "general"


@dataclass(frozen=True, slots=True)
class SkillCatalogSnapshot:
    entries: tuple[SkillCatalogEntry, ...]
    query_latency_ms: float
    scanned_count: int
    filtered_reasons: dict[str, int]


class SkillCatalog:
    """只查询轻量 Metadata；未选择前不读取 instructions 或 resources。"""

    def __init__(self, session: AsyncSession, context: TenantContext) -> None:
        self.session = session
        self.context = context

    async def available(self) -> list[SkillCatalogEntry]:
        return list((await self.snapshot()).entries)

    async def snapshot(self) -> SkillCatalogSnapshot:
        """只扫描当前租户版本化 Metadata，并记录非敏感过滤分类与查询耗时。"""
        started = time.perf_counter()
        if PermissionCode.COPILOT_SKILL_RUN.value not in self.context.permission_codes:
            return SkillCatalogSnapshot(
                (), round((time.perf_counter() - started) * 1000, 3), 0, {"MISSING_RUN_PERMISSION": 1}
            )
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
                    SkillVersion.source_metadata,
                    Skill.enabled,
                    Skill.approval_status,
                    SkillVersion.approval_status,
                    SkillVersion.risk_level,
                )
                .join(
                    SkillVersion,
                    (SkillVersion.tenant_id == Skill.tenant_id)
                    & (SkillVersion.skill_id == Skill.id)
                    & (SkillVersion.version == Skill.current_version),
                )
                .where(Skill.tenant_id == self.context.tenant_id)
                .order_by(Skill.id)
            )
        ).all()
        permissions = self.context.permission_codes
        entries: list[SkillCatalogEntry] = []
        filtered: dict[str, int] = {}
        for row in rows:
            reason = None
            if not row[8]:
                reason = "DISABLED"
            elif row[9] != "APPROVED" or row[10] != "APPROVED":
                reason = "NOT_APPROVED"
            elif row[11] != "READ_ONLY":
                reason = "RISK_NOT_ALLOWED"
            elif not set(row[6]).issubset(permissions):
                reason = "PERMISSION_DENIED"
            if reason:
                filtered[reason] = filtered.get(reason, 0) + 1
                continue
            metadata = row[7] or {}
            nested = metadata.get("metadata") if isinstance(metadata, dict) else None
            category = (
                str(nested.get("neorvion-category") or "general")
                if isinstance(nested, dict)
                else str(metadata.get("category") or "general")
            )
            entries.append(
                SkillCatalogEntry(
                    skill_id=row[0],
                    version_id=row[1],
                    skill_key=row[2],
                    name=row[3],
                    description=row[4],
                    version=row[5],
                    metadata=metadata,
                    required_permissions=tuple(str(value) for value in row[6]),
                    category=category,
                )
            )
        return SkillCatalogSnapshot(
            tuple(entries),
            round((time.perf_counter() - started) * 1000, 3),
            len(rows),
            filtered,
        )
