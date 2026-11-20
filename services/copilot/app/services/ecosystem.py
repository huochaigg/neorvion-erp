from __future__ import annotations

import difflib
import hashlib
import io
import json
import os
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

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
from app.models.ecosystem import (
    McpServer,
    McpToolVersion,
    Skill,
    SkillExecutionPlan,
    SkillExecutionPlanStep,
    SkillRun,
    SkillVersion,
)
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
    SkillPlanOut,
    SkillPlanStepOut,
    SkillRunOut,
    SkillTemplateImportOut,
    SkillVersionDiffOut,
    SkillVersionIn,
    SkillVersionOut,
)
from app.skills.parser import SkillParser
from app.tools.registry import build_tool_registry


class EcosystemService:
    _TEMPLATE_KEYS = frozenset(
        {"inventory-analysis", "sales-order-review", "knowledge-research"}
    )
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

    async def import_skill_templates(
        self, skill_keys: list[str] | None = None
    ) -> list[SkillTemplateImportOut]:
        """以 JSON 治理模板导入标准 SKILL.md 快照；已审核配置绝不被磁盘覆盖。"""
        requested = set(skill_keys or self._TEMPLATE_KEYS)
        unknown = requested - self._TEMPLATE_KEYS
        if unknown:
            raise AppError("包含未知 Skill 模板", code=42288, status_code=422)
        base = Path(__file__).resolve().parents[2] / "skills"
        outputs: list[SkillTemplateImportOut] = []
        for key in sorted(requested):
            try:
                payload = SkillCreate.model_validate_json((base / f"{key}.json").read_text("utf-8"))
                definition = SkillParser().parse_directory(base / key)
                payload = payload.model_copy(
                    update={
                        "description": definition.description,
                        "version": payload.version.model_copy(
                            update={
                                "instructions": definition.instructions,
                                "source_format": "SKILL_MD",
                                "source_metadata": definition.frontmatter,
                                "resources": definition.resources,
                            }
                        ),
                    }
                )
            except (OSError, ValueError) as exc:
                raise AppError("内置 Skill 模板无效", code=50086, status_code=500) from exc
            await self._validate_skill_dependencies(payload.version)
            canonical = self._skill_content(payload.version)
            content_hash = hashlib.sha256(canonical.encode()).hexdigest()
            row = await self.session.scalar(
                select(Skill).where(
                    Skill.tenant_id == self.context.tenant_id,
                    Skill.skill_key == key,
                ).with_for_update()
            )
            if row is None:
                row = Skill(
                    tenant_id=self.context.tenant_id,
                    skill_key=payload.skill_key,
                    name=payload.name,
                    description=payload.description,
                    created_by=self.context.user_id,
                    updated_by=self.context.user_id,
                )
                self.session.add(row)
                await self.session.flush()
                version = await self._add_skill_version(row, payload.version)
                status = "IMPORTED"
                self._audit("SKILL_TEMPLATE_IMPORTED", "skill", str(row.id), {"key": key})
            else:
                current = await self._current_skill_version(row)
                current_payload = SkillVersionIn.model_validate(current, from_attributes=True)
                current_semantic_hash = hashlib.sha256(
                    self._skill_content(current_payload).encode()
                ).hexdigest()
                row.name = payload.name
                row.description = payload.description
                row.updated_by = self.context.user_id
                if current.content_hash == content_hash or current_semantic_hash == content_hash:
                    version = current
                    status = "UNCHANGED"
                elif row.enabled or row.approval_status == "APPROVED" or current.approval_status == "APPROVED":
                    version = current
                    status = "PROTECTED"
                else:
                    version = await self._add_skill_version(row, payload.version)
                    row.enabled = False
                    row.approval_status = "PENDING_APPROVAL"
                    status = "IMPORTED"
                    self._audit(
                        "SKILL_TEMPLATE_IMPORTED",
                        "skill",
                        str(row.id),
                        {"key": key, "version": version.version},
                    )
            outputs.append(
                SkillTemplateImportOut(
                    skill_key=key,
                    skill_id=row.id,
                    version=version.version,
                    status=status,
                )
            )
        await self.session.commit()
        return outputs

    async def import_skill_package(self, archive: bytes) -> SkillTemplateImportOut:
        """导入 SKILL.md、references 和治理 sidecar；不释放或执行任何脚本。"""
        if not archive or len(archive) > 262_144:
            raise AppError("Skill 包为空或超过 256 KiB", code=42292, status_code=422)
        try:
            zipped = zipfile.ZipFile(io.BytesIO(archive))
        except zipfile.BadZipFile as exc:
            raise AppError("Skill 包不是有效 ZIP", code=42292, status_code=422) from exc
        members = [item for item in zipped.infolist() if not item.is_dir()]
        if len(members) > 16 or sum(item.file_size for item in members) > 196_608:
            raise AppError("Skill 包文件数量或解压大小超过限制", code=42292, status_code=422)
        roots: set[str] = set()
        selected: dict[str, bytes] = {}
        for item in members:
            normalized = item.filename.replace("\\", "/")
            parts = Path(normalized).parts
            if (
                item.flag_bits & 0x1
                or normalized.startswith("/")
                or ".." in parts
                or len(parts) < 2
                or item.file_size > 65_536
                or (item.compress_size and item.file_size / item.compress_size > 100)
            ):
                raise AppError("Skill 包包含不安全路径或压缩项", code=42292, status_code=422)
            roots.add(parts[0])
            relative = "/".join(parts[1:])
            allowed = relative in {"SKILL.md", "governance.json"} or (
                relative.startswith("references/")
                and len(Path(relative).parts) == 2
                and relative.endswith(".md")
            )
            if allowed:
                selected[relative] = zipped.read(item)
        if len(roots) != 1 or "SKILL.md" not in selected or "governance.json" not in selected:
            raise AppError(
                "Skill 包必须只有一个根目录并包含 SKILL.md 与 governance.json",
                code=42292,
                status_code=422,
            )
        with tempfile.TemporaryDirectory(prefix="neorvion-skill-") as temporary:
            root = Path(temporary) / next(iter(roots))
            for relative, content in selected.items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            definition = SkillParser().parse_directory(root)
            try:
                payload = SkillCreate.model_validate_json(selected["governance.json"])
            except ValueError as exc:
                raise AppError("governance.json 无效", code=42292, status_code=422) from exc
        if payload.skill_key != definition.name:
            raise AppError(
                "governance.json skill_key 与 SKILL.md name 不一致",
                code=42292,
                status_code=422,
            )
        payload = payload.model_copy(
            update={
                "description": definition.description,
                "version": payload.version.model_copy(
                    update={
                        "instructions": definition.instructions,
                        "source_format": "SKILL_MD",
                        "source_metadata": definition.frontmatter,
                        "resources": definition.resources,
                    }
                ),
            }
        )
        await self._validate_skill_dependencies(payload.version)
        content_hash = hashlib.sha256(self._skill_content(payload.version).encode()).hexdigest()
        row = await self.session.scalar(
            select(Skill)
            .where(
                Skill.tenant_id == self.context.tenant_id,
                Skill.skill_key == payload.skill_key,
            )
            .with_for_update()
        )
        if row is None:
            row = Skill(
                tenant_id=self.context.tenant_id,
                skill_key=payload.skill_key,
                name=payload.name,
                description=payload.description,
                created_by=self.context.user_id,
                updated_by=self.context.user_id,
            )
            self.session.add(row)
            await self.session.flush()
            version = await self._add_skill_version(row, payload.version)
            status = "IMPORTED"
        else:
            current = await self._current_skill_version(row)
            row.name = payload.name
            row.description = payload.description
            row.updated_by = self.context.user_id
            if current.content_hash == content_hash:
                version, status = current, "UNCHANGED"
            elif (
                row.enabled
                or row.approval_status == "APPROVED"
                or current.approval_status == "APPROVED"
            ):
                version, status = current, "PROTECTED"
            else:
                version = await self._add_skill_version(row, payload.version)
                row.enabled = False
                row.approval_status = "PENDING_APPROVAL"
                status = "IMPORTED"
        self._audit("SKILL_PACKAGE_IMPORTED", "skill", str(row.id), {"status": status})
        await self.session.commit()
        return SkillTemplateImportOut(
            skill_key=row.skill_key,
            skill_id=row.id,
            version=version.version,
            status=status,
        )

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
            payload = SkillVersionIn.model_validate(version, from_attributes=True)
            await self._validate_skill_dependencies(payload)
            await self._validate_skill_graph(row, payload)
        version.approval_status = "APPROVED" if approved else "REJECTED"
        row.approval_status = version.approval_status
        row.enabled = False
        row.updated_by = self.context.user_id
        self._audit("SKILL_REVIEWED", "skill", str(row.id), {"approved": approved})
        await self.session.commit()
        return await self.skill(row.id)

    async def set_skill_enabled(self, skill_id: int, enabled: bool) -> SkillDetailOut:
        row = await self._skill(skill_id, lock=True)
        if enabled and row.approval_status != "APPROVED":
            raise AppError("Skill 审核通过前不能启用", code=40984, status_code=409)
        if enabled:
            version = await self._current_skill_version(row)
            payload = SkillVersionIn.model_validate(version, from_attributes=True)
            await self._validate_skill_dependencies(payload)
            await self._validate_skill_graph(row, payload)
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

    async def set_skill_deprecated(self, skill_id: int, deprecated: bool) -> SkillDetailOut:
        """标记弃用时立即禁止新选择；撤销弃用后必须重新审核，绝不恢复旧授权。"""
        row = await self._skill(skill_id, lock=True)
        version = await self._current_skill_version(row)
        status = "DEPRECATED" if deprecated else "PENDING_APPROVAL"
        row.approval_status = status
        row.enabled = False
        row.updated_by = self.context.user_id
        version.approval_status = status
        self._audit(
            "SKILL_DEPRECATED" if deprecated else "SKILL_DEPRECATION_REVOKED",
            "skill",
            str(row.id),
            {"version": version.version},
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
        payload = SkillVersionIn.model_validate(version, from_attributes=True)
        await self._validate_skill_dependencies(payload)
        await self._validate_skill_graph(row, payload)
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
        filters = [
            SkillRun.tenant_id == self.context.tenant_id,
            SkillRun.skill_id == skill_id,
        ]
        if PermissionCode.COPILOT_SKILL_MANAGE.value not in self.context.permission_codes:
            filters.append(SkillRun.user_id == self.context.user_id)
        rows = (
            await self.session.scalars(
                select(SkillRun)
                .where(*filters)
                .order_by(SkillRun.created_at.desc())
                .limit(min(max(limit, 1), 100))
            )
        ).all()
        return [SkillRunOut.model_validate(row) for row in rows]

    async def skill_run(self, skill_id: int, run_id: int) -> SkillRunOut:
        await self._skill(skill_id)
        filters = [
            SkillRun.tenant_id == self.context.tenant_id,
            SkillRun.skill_id == skill_id,
            SkillRun.id == run_id,
        ]
        if PermissionCode.COPILOT_SKILL_MANAGE.value not in self.context.permission_codes:
            filters.append(SkillRun.user_id == self.context.user_id)
        row = await self.session.scalar(
            select(SkillRun).where(*filters)
        )
        if row is None:
            raise AppError("SkillRun 不存在", code=40485, status_code=404)
        return SkillRunOut.model_validate(row)

    async def skill_plan(self, plan_id: int) -> SkillPlanOut:
        filters = [
            SkillExecutionPlan.tenant_id == self.context.tenant_id,
            SkillExecutionPlan.id == plan_id,
        ]
        if PermissionCode.COPILOT_SKILL_MANAGE.value not in self.context.permission_codes:
            filters.append(SkillExecutionPlan.user_id == self.context.user_id)
        plan = await self.session.scalar(select(SkillExecutionPlan).where(*filters))
        if plan is None:
            raise AppError("Skill Plan 不存在", code=40488, status_code=404)
        steps = (
            await self.session.scalars(
                select(SkillExecutionPlanStep)
                .where(
                    SkillExecutionPlanStep.tenant_id == self.context.tenant_id,
                    SkillExecutionPlanStep.plan_id == plan.id,
                )
                .order_by(SkillExecutionPlanStep.position)
            )
        ).all()
        return SkillPlanOut(
            **SkillPlanOut.model_validate(plan).model_dump(exclude={"steps"}),
            steps=[SkillPlanStepOut.model_validate(item) for item in steps],
        )

    async def skill_version_diff(
        self, skill_id: int, from_version: int, to_version: int
    ) -> SkillVersionDiffOut:
        await self._skill(skill_id)
        rows = (
            await self.session.scalars(
                select(SkillVersion).where(
                    SkillVersion.tenant_id == self.context.tenant_id,
                    SkillVersion.skill_id == skill_id,
                    SkillVersion.version.in_({from_version, to_version}),
                )
            )
        ).all()
        versions = {item.version: item for item in rows}
        if from_version not in versions or to_version not in versions:
            raise AppError("Skill 对比版本不存在", code=40484, status_code=404)
        before, after = versions[from_version], versions[to_version]
        fields = (
            "instructions",
            "input_schema",
            "output_schema",
            "allowed_agents",
            "required_permissions",
            "allowed_tools",
            "resources",
            "source_metadata",
            "timeout_seconds",
            "token_budget",
        )
        changed = [name for name in fields if getattr(before, name) != getattr(after, name)]
        lines = list(
            difflib.unified_diff(
                before.instructions.splitlines(),
                after.instructions.splitlines(),
                fromfile=f"v{from_version}",
                tofile=f"v{to_version}",
                lineterm="",
            )
        )[:500]
        return SkillVersionDiffOut(
            skill_id=skill_id,
            from_version=from_version,
            to_version=to_version,
            changed_fields=changed,
            instructions_diff=lines,
        )

    async def _add_skill_version(self, row: Skill, payload: SkillVersionIn) -> SkillVersion:
        await self._validate_skill_dependencies(payload)
        await self._validate_skill_graph(row, payload)
        version_number = row.current_version + 1
        canonical = self._skill_content(payload)
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
        registry = build_agent_registry()
        agents = {item.agent_name for item in registry.all()}
        if not set(payload.allowed_agents).issubset(agents - {"supervisor_agent"}):
            raise AppError("Skill Agent 白名单无效", code=42286, status_code=422)
        tool_registry = build_tool_registry()
        builtins = tool_registry.names
        if set(payload.allowed_tools) & build_action_registry().names:
            raise AppError("Skill 只允许使用只读查询工具", code=42286, status_code=422)
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
        for agent_name in payload.allowed_agents:
            spec = registry.get(agent_name)
            unsupported = set(payload.allowed_tools) - spec.allowed_tools - dynamic_names
            if unsupported:
                raise AppError("Skill Agent 与工具白名单不兼容", code=42286, status_code=422)
        required = set(payload.required_permissions)
        for tool_name in set(payload.allowed_tools) & builtins:
            spec = tool_registry.get(tool_name)
            assert spec is not None
            if not {spec.permission, *spec.additional_permissions}.issubset(required):
                raise AppError("Skill 未声明工具所需权限", code=42286, status_code=422)
        if len(payload.allowed_tools) == 1:
            spec = tool_registry.get(payload.allowed_tools[0])
            if spec is not None:
                tool_schema = spec.args_model.model_json_schema()
                if not set(tool_schema.get("required", [])).issubset(
                    set(payload.input_schema.get("required", []))
                ):
                    raise AppError("Skill 输入缺少工具必填参数", code=42286, status_code=422)
        validate_tool_schema(payload.input_schema)
        validate_tool_schema(payload.output_schema)

    async def _validate_skill_graph(self, row: Skill, payload: SkillVersionIn) -> None:
        """校验声明依赖存在、已审核且不会形成循环；依赖不会扩大本 Skill 权限。"""
        dependencies = [str(item) for item in payload.source_metadata.get("dependencies", [])]
        if row.skill_key in dependencies:
            raise AppError("Skill 不能依赖自身", code=42288, status_code=422)
        rows = (
            await self.session.execute(
                select(Skill, SkillVersion)
                .join(
                    SkillVersion,
                    (SkillVersion.tenant_id == Skill.tenant_id)
                    & (SkillVersion.skill_id == Skill.id)
                    & (SkillVersion.version == Skill.current_version),
                )
                .where(Skill.tenant_id == self.context.tenant_id)
            )
        ).all()
        known = {skill.skill_key: (skill, version) for skill, version in rows}
        for key in dependencies:
            pair = known.get(key)
            if pair is None or pair[0].approval_status != "APPROVED" or pair[1].approval_status != "APPROVED":
                raise AppError("Skill 依赖不存在或未审核", code=42288, status_code=422)
            if not set(pair[1].required_permissions).issubset(payload.required_permissions):
                raise AppError("Skill 依赖不能隐式扩大权限", code=42288, status_code=422)
        graph = {
            key: [str(item) for item in version.source_metadata.get("dependencies", [])]
            for key, (_, version) in known.items()
        }
        graph[row.skill_key] = dependencies
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(key: str) -> None:
            if key in visiting:
                raise AppError("Skill 依赖存在循环", code=42288, status_code=422)
            if key in visited:
                return
            visiting.add(key)
            for dependency in graph.get(key, []):
                visit(dependency)
            visiting.remove(key)
            visited.add(key)

        visit(row.skill_key)

    @staticmethod
    def _skill_content(payload: SkillVersionIn) -> str:
        return json.dumps(
            payload.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

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
