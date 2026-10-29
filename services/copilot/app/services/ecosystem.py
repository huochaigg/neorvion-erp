from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.actions.registry import build_action_registry
from app.agents.registry import build_agent_registry
from app.core.exceptions import AppError
from app.core.permissions import PermissionCode
from app.core.tenant import TenantContext
from app.mcp.security import validate_endpoint, validate_tool_schema
from app.mcp.transport import StreamableHttpTransport
from app.models.ecosystem import McpServer, McpToolVersion, Skill, SkillRun, SkillVersion
from app.models.governance import AIGovernanceAudit
from app.schemas.ecosystem import (
    McpServerCreate,
    McpServerOut,
    McpServerPatch,
    McpToolOut,
    McpToolReviewIn,
    SkillCreate,
    SkillDetailOut,
    SkillOut,
    SkillRunOut,
    SkillVersionIn,
    SkillVersionOut,
)
from app.tools.registry import build_tool_registry


class EcosystemService:
    def __init__(self, session: AsyncSession, context: TenantContext, request_id: str = "") -> None:
        self.session = session
        self.context = context
        self.request_id = request_id

    async def servers(self) -> list[McpServerOut]:
        rows = (
            await self.session.scalars(
                select(McpServer)
                .where(McpServer.tenant_id == self.context.tenant_id)
                .order_by(McpServer.updated_at.desc())
            )
        ).all()
        return [self._server_out(row) for row in rows]

    async def create_server(self, payload: McpServerCreate) -> McpServerOut:
        endpoint = validate_endpoint(str(payload.endpoint))
        if payload.authentication_type == "BEARER_ENV" and not payload.credential_reference:
            raise AppError("Bearer MCP 必须配置 Secret 引用", code=42283, status_code=422)
        row = McpServer(
            tenant_id=self.context.tenant_id,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
            endpoint=endpoint,
            **payload.model_dump(exclude={"endpoint"}),
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("MCP Server Key 已存在", code=40981, status_code=409) from exc
        self._audit("MCP_SERVER_CREATED", "mcp_server", str(row.id), {"key": row.server_key})
        await self.session.commit()
        await self.session.refresh(row)
        return self._server_out(row)

    async def patch_server(self, server_id: int, payload: McpServerPatch) -> McpServerOut:
        row = await self._server(server_id, lock=True)
        values = payload.model_dump(exclude_unset=True)
        if "endpoint" in values:
            values["endpoint"] = validate_endpoint(str(values["endpoint"]))
        for key, value in values.items():
            setattr(row, key, value)
        if row.authentication_type == "BEARER_ENV" and not row.credential_reference:
            raise AppError("Bearer MCP 必须配置 Secret 引用", code=42283, status_code=422)
        row.configuration_version += 1
        row.enabled = False
        row.approval_status = "PENDING_APPROVAL"
        row.health_status = "UNKNOWN"
        row.updated_by = self.context.user_id
        self._audit("MCP_SERVER_CHANGED", "mcp_server", str(row.id), {"fields": sorted(values)})
        await self.session.commit()
        return self._server_out(row)

    async def review_server(self, server_id: int, approved: bool) -> McpServerOut:
        row = await self._server(server_id, lock=True)
        row.approval_status = "APPROVED" if approved else "REJECTED"
        row.enabled = bool(approved and row.health_status == "HEALTHY")
        row.updated_by = self.context.user_id
        self._audit(
            "MCP_SERVER_REVIEWED",
            "mcp_server",
            str(row.id),
            {"approved": approved},
        )
        await self.session.commit()
        return self._server_out(row)

    async def set_server_enabled(self, server_id: int, enabled: bool) -> McpServerOut:
        row = await self._server(server_id, lock=True)
        if enabled and (row.approval_status != "APPROVED" or row.health_status != "HEALTHY"):
            raise AppError("MCP Server 审核和健康检查通过前不能启用", code=40982, status_code=409)
        row.enabled = enabled
        row.updated_by = self.context.user_id
        self._audit(
            "MCP_SERVER_ENABLED" if enabled else "MCP_SERVER_DISABLED",
            "mcp_server",
            str(row.id),
            {},
        )
        await self.session.commit()
        return self._server_out(row)

    async def discover(self, server_id: int) -> list[McpToolOut]:
        """发现只创建待审核 Schema 版本；Schema 变化会停用旧版本。"""
        server = await self._server(server_id)
        await self.session.commit()
        tools = await StreamableHttpTransport(server).list_tools()
        server = await self._server(server_id, lock=True)
        accepted: list[McpToolVersion] = []
        seen_names: set[str] = set()
        builtins = build_tool_registry().names | build_action_registry().names
        for item in tools:
            name = str(item.get("name") or "")
            if not name or name in seen_names or name in builtins:
                raise AppError(
                    "MCP 工具名称为空、重复或与内置工具冲突", code=42284, status_code=422
                )
            seen_names.add(name)
            if server.allowed_tools and name not in set(server.allowed_tools):
                continue
            if name in set(server.denied_tools):
                continue
            schema = validate_tool_schema(item.get("inputSchema"))
            canonical = json.dumps(schema, sort_keys=True, separators=(",", ":"))
            schema_hash = hashlib.sha256(canonical.encode()).hexdigest()
            current = await self.session.scalar(
                select(McpToolVersion)
                .where(
                    McpToolVersion.tenant_id == self.context.tenant_id,
                    McpToolVersion.server_id == server.id,
                    McpToolVersion.tool_name == name,
                    McpToolVersion.superseded_at.is_(None),
                )
                .with_for_update()
            )
            if current is not None and current.schema_hash == schema_hash:
                accepted.append(current)
                continue
            if current is not None:
                current.enabled = False
                current.approval_status = "SCHEMA_CHANGED"
                current.superseded_at = datetime.now(UTC)
            qualified = f"mcp__{server.server_key}__{name}"
            row = McpToolVersion(
                tenant_id=self.context.tenant_id,
                server_id=server.id,
                tool_name=name,
                qualified_name=qualified,
                description=str(item.get("description") or "")[:2000],
                input_schema=schema,
                schema_hash=schema_hash,
                configuration_version=server.configuration_version,
                required_permissions=[],
                resource_requirements={},
                allowed_agents=[],
                risk_level="READ_ONLY",
                timeout_seconds=min(server.timeout_seconds, 30),
                enabled=False,
                approval_status="PENDING_APPROVAL",
            )
            self.session.add(row)
            accepted.append(row)
        server.health_status = "HEALTHY"
        server.last_checked_at = datetime.now(UTC)
        await self.session.flush()
        self._audit("MCP_TOOLS_DISCOVERED", "mcp_server", str(server.id), {"count": len(accepted)})
        await self.session.commit()
        return [McpToolOut.model_validate(row) for row in accepted]

    async def probe(self, server_id: int) -> McpServerOut:
        row = await self._server(server_id)
        await self.session.commit()
        try:
            await StreamableHttpTransport(row).list_tools()
            row = await self._server(server_id, lock=True)
            row.health_status = "HEALTHY"
        except AppError:
            row = await self._server(server_id, lock=True)
            row.health_status = "UNAVAILABLE"
        row.last_checked_at = datetime.now(UTC)
        self._audit("MCP_SERVER_PROBED", "mcp_server", str(row.id), {"status": row.health_status})
        await self.session.commit()
        return self._server_out(row)

    async def tools(self) -> list[McpToolOut]:
        rows = (
            await self.session.scalars(
                select(McpToolVersion)
                .where(McpToolVersion.tenant_id == self.context.tenant_id)
                .order_by(McpToolVersion.created_at.desc())
            )
        ).all()
        return [McpToolOut.model_validate(row) for row in rows]

    async def review_tool(self, tool_id: int, payload: McpToolReviewIn) -> McpToolOut:
        row = await self._tool(tool_id, lock=True)
        server = await self._server(row.server_id)
        if payload.approved and server.approval_status != "APPROVED":
            raise AppError("MCP Server 审核通过前不能启用工具", code=40982, status_code=409)
        known = {item.value for item in PermissionCode}
        if not set(payload.required_permissions).issubset(known):
            raise AppError("MCP 工具引用了未知权限", code=42285, status_code=422)
        agents = {item.agent_name for item in build_agent_registry().all()}
        if not set(payload.allowed_agents).issubset(agents - {"supervisor_agent"}):
            raise AppError("MCP 工具 Agent 白名单无效", code=42285, status_code=422)
        row.required_permissions = sorted(set(payload.required_permissions))
        row.resource_requirements = payload.resource_requirements
        row.allowed_agents = sorted(set(payload.allowed_agents))
        row.timeout_seconds = payload.timeout_seconds
        row.approval_status = "APPROVED" if payload.approved else "REJECTED"
        row.enabled = payload.approved
        row.reviewed_by = self.context.user_id
        self._audit("MCP_TOOL_REVIEWED", "mcp_tool", str(row.id), {"approved": payload.approved})
        await self.session.commit()
        return McpToolOut.model_validate(row)

    async def skills(self) -> list[SkillOut]:
        rows = (
            await self.session.scalars(
                select(Skill)
                .where(Skill.tenant_id == self.context.tenant_id)
                .order_by(Skill.updated_at.desc())
            )
        ).all()
        return [SkillOut.model_validate(row) for row in rows]

    async def create_skill(self, payload: SkillCreate) -> SkillDetailOut:
        row = Skill(
            tenant_id=self.context.tenant_id,
            skill_key=payload.skill_key,
            name=payload.name,
            description=payload.description,
            created_by=self.context.user_id,
            updated_by=self.context.user_id,
        )
        self.session.add(row)
        try:
            await self.session.flush()
            version = await self._add_skill_version(row, payload.version)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppError("Skill Key 已存在", code=40983, status_code=409) from exc
        self._audit("SKILL_CREATED", "skill", str(row.id), {"version": version.version})
        await self.session.commit()
        return await self.skill(row.id)

    async def add_skill_version(self, skill_id: int, payload: SkillVersionIn) -> SkillDetailOut:
        row = await self._skill(skill_id, lock=True)
        await self._add_skill_version(row, payload)
        row.enabled = False
        row.approval_status = "PENDING_APPROVAL"
        row.updated_by = self.context.user_id
        self._audit("SKILL_VERSION_CREATED", "skill", str(row.id), {"version": row.current_version})
        await self.session.commit()
        return await self.skill(row.id)

    async def review_skill(self, skill_id: int, approved: bool) -> SkillDetailOut:
        row = await self._skill(skill_id, lock=True)
        version = await self._current_skill_version(row)
        if approved:
            await self._validate_skill_dependencies(
                SkillVersionIn.model_validate(version, from_attributes=True)
            )
        version.approval_status = "APPROVED" if approved else "REJECTED"
        row.approval_status = version.approval_status
        row.enabled = approved
        row.updated_by = self.context.user_id
        self._audit("SKILL_REVIEWED", "skill", str(row.id), {"approved": approved})
        await self.session.commit()
        return await self.skill(row.id)

    async def set_skill_enabled(self, skill_id: int, enabled: bool) -> SkillDetailOut:
        row = await self._skill(skill_id, lock=True)
        if enabled and row.approval_status != "APPROVED":
            raise AppError("Skill 审核通过前不能启用", code=40984, status_code=409)
        row.enabled = enabled
        row.updated_by = self.context.user_id
        self._audit(
            "SKILL_ENABLED" if enabled else "SKILL_DISABLED",
            "skill",
            str(row.id),
            {},
        )
        await self.session.commit()
        return await self.skill(row.id)

    async def rollback_skill(self, skill_id: int, version_number: int) -> SkillDetailOut:
        """把当前指针恢复到历史快照；为防止旧授权复活，恢复后必须重新审核。"""
        row = await self._skill(skill_id, lock=True)
        version = await self.session.scalar(
            select(SkillVersion).where(
                SkillVersion.tenant_id == self.context.tenant_id,
                SkillVersion.skill_id == row.id,
                SkillVersion.version == version_number,
            )
        )
        if version is None:
            raise AppError("Skill 历史版本不存在", code=40484, status_code=404)
        await self._validate_skill_dependencies(
            SkillVersionIn.model_validate(version, from_attributes=True)
        )
        row.current_version = version_number
        row.enabled = False
        row.approval_status = "PENDING_APPROVAL"
        version.approval_status = "PENDING_APPROVAL"
        row.updated_by = self.context.user_id
        self._audit(
            "SKILL_ROLLED_BACK",
            "skill",
            str(row.id),
            {"version": version_number},
        )
        await self.session.commit()
        return await self.skill(row.id)

    async def skill(self, skill_id: int) -> SkillDetailOut:
        row = await self._skill(skill_id)
        versions = (
            await self.session.scalars(
                select(SkillVersion)
                .where(
                    SkillVersion.tenant_id == self.context.tenant_id,
                    SkillVersion.skill_id == row.id,
                )
                .order_by(SkillVersion.version.desc())
            )
        ).all()
        return SkillDetailOut(
            **SkillOut.model_validate(row).model_dump(),
            versions=[SkillVersionOut.model_validate(item) for item in versions],
        )

    async def skill_runs(self, skill_id: int, limit: int = 50) -> list[SkillRunOut]:
        await self._skill(skill_id)
        rows = (
            await self.session.scalars(
                select(SkillRun)
                .where(
                    SkillRun.tenant_id == self.context.tenant_id,
                    SkillRun.skill_id == skill_id,
                )
                .order_by(SkillRun.created_at.desc())
                .limit(min(max(limit, 1), 100))
            )
        ).all()
        return [SkillRunOut.model_validate(row) for row in rows]

    async def _add_skill_version(self, row: Skill, payload: SkillVersionIn) -> SkillVersion:
        await self._validate_skill_dependencies(payload)
        version_number = row.current_version + 1
        canonical = json.dumps(payload.model_dump(), sort_keys=True, default=str)
        version = SkillVersion(
            tenant_id=self.context.tenant_id,
            skill_id=row.id,
            version=version_number,
            content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
            created_by=self.context.user_id,
            **payload.model_dump(),
        )
        self.session.add(version)
        row.current_version = version_number
        await self.session.flush()
        return version

    async def _validate_skill_dependencies(self, payload: SkillVersionIn) -> None:
        known_permissions = {item.value for item in PermissionCode}
        if not set(payload.required_permissions).issubset(known_permissions):
            raise AppError("Skill 引用了未知权限", code=42286, status_code=422)
        agents = {item.agent_name for item in build_agent_registry().all()}
        if not set(payload.allowed_agents).issubset(agents - {"supervisor_agent"}):
            raise AppError("Skill Agent 白名单无效", code=42286, status_code=422)
        builtins = build_tool_registry().names | build_action_registry().names
        dynamic_names = {
            item
            for item in (
                await self.session.scalars(
                    select(McpToolVersion.qualified_name).where(
                        McpToolVersion.tenant_id == self.context.tenant_id,
                        McpToolVersion.enabled.is_(True),
                        McpToolVersion.approval_status == "APPROVED",
                        McpToolVersion.superseded_at.is_(None),
                    )
                )
            ).all()
        }
        for tool in payload.allowed_tools:
            if tool not in builtins and tool not in dynamic_names:
                raise AppError("Skill 引用了未注册工具", code=42286, status_code=422)
        validate_tool_schema(payload.input_schema)
        validate_tool_schema(payload.output_schema)

    async def _server(self, server_id: int, lock: bool = False) -> McpServer:
        stmt = select(McpServer).where(
            McpServer.tenant_id == self.context.tenant_id, McpServer.id == server_id
        )
        row = await self.session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise AppError("MCP Server 不存在", code=40481, status_code=404)
        return row

    async def _tool(self, tool_id: int, lock: bool = False) -> McpToolVersion:
        stmt = select(McpToolVersion).where(
            McpToolVersion.tenant_id == self.context.tenant_id,
            McpToolVersion.id == tool_id,
        )
        row = await self.session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise AppError("MCP 工具不存在", code=40482, status_code=404)
        return row

    async def _skill(self, skill_id: int, lock: bool = False) -> Skill:
        stmt = select(Skill).where(Skill.tenant_id == self.context.tenant_id, Skill.id == skill_id)
        row = await self.session.scalar(stmt.with_for_update() if lock else stmt)
        if row is None:
            raise AppError("Skill 不存在", code=40483, status_code=404)
        return row

    async def _current_skill_version(self, row: Skill) -> SkillVersion:
        version = await self.session.scalar(
            select(SkillVersion).where(
                SkillVersion.tenant_id == self.context.tenant_id,
                SkillVersion.skill_id == row.id,
                SkillVersion.version == row.current_version,
            )
        )
        if version is None:
            raise AppError("Skill 当前版本不存在", code=40983, status_code=409)
        return version

    @staticmethod
    def _server_out(row: McpServer) -> McpServerOut:
        return McpServerOut(
            **{
                column.name: getattr(row, column.name)
                for column in row.__table__.columns
                if column.name not in {"tenant_id", "created_by", "updated_by"}
            },
            credential_configured=bool(
                row.credential_reference and os.getenv(row.credential_reference, "")
            ),
        )

    def _audit(self, action: str, target_type: str, target_id: str, detail: dict) -> None:
        self.session.add(
            AIGovernanceAudit(
                tenant_id=self.context.tenant_id,
                actor_user_id=self.context.user_id,
                actor_type="USER",
                action=action,
                target_type=target_type,
                target_id=target_id,
                outcome="SUCCEEDED",
                safe_detail=detail,
                request_id=self.request_id,
            )
        )
