from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError

from app.actions.registry import ActionRegistry, build_action_registry
from app.actions.schemas import ProposeActionArgs, ValidateActionProposalArgs
from app.ai.types import ModelToolCall, ModelToolDefinition
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.tenant import TenantContext
from app.erp.client import ErpApiClient
from app.knowledge.client import KnowledgeApiClient
from app.schemas.action_proposal import ActionProposalCreate
from app.tools.registry import ToolRegistry

if TYPE_CHECKING:
    from app.services.action_proposals import ActionProposalService


@dataclass(slots=True)
class ToolRuntime:
    tenant: TenantContext
    access_token: str
    erp_audience_authorized: bool
    knowledge_audience_authorized: bool = False
    request_id: str = ""
    started_at: float = field(default_factory=time.monotonic)
    calls: int = 0
    evidences: list[dict[str, Any]] = field(default_factory=list)
    proposal_service: ActionProposalService | None = None
    conversation_id: int | None = None
    source_message_id: int | None = None
    allowed_tools: frozenset[str] | None = None
    max_calls_override: int | None = None
    shared_calls: list[int] | None = None
    global_call_limit: int | None = None


@dataclass(frozen=True, slots=True)
class ToolExecutionResult:
    content: str
    event: dict[str, Any]
    evidences: tuple[dict[str, Any], ...] = ()


class ToolExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        client: ErpApiClient,
        knowledge_client: KnowledgeApiClient | None = None,
        action_registry: ActionRegistry | None = None,
    ) -> None:
        self.registry = registry
        self.client = client
        self.knowledge_client = knowledge_client
        self.action_registry = action_registry or build_action_registry()

    def definitions(
        self,
        permissions: frozenset[str],
        *,
        allowed_tools: frozenset[str] | None = None,
    ) -> list[ModelToolDefinition]:
        definitions: list[ModelToolDefinition] = [
            *self.registry.definitions(permissions),
            *self.action_registry.definitions(permissions),
        ]
        if allowed_tools is None:
            return definitions
        return [item for item in definitions if str(item["function"].get("name")) in allowed_tools]

    async def execute(self, call: ModelToolCall, runtime: ToolRuntime) -> ToolExecutionResult:
        """在模型之外执行工具白名单、参数、权限、预算和结果大小校验。"""
        if runtime.allowed_tools is not None and call.name not in runtime.allowed_tools:
            raise AppError("Agent 无权调用该工具", code=40378, status_code=403)
        if call.name in {"propose_action", "validate_action_proposal"}:
            return await self._execute_proposal(call, runtime)
        spec = self.registry.get(call.name)
        if spec is None:
            raise AppError("模型请求了未注册的工具", code=40072, status_code=400)
        required_permissions = (spec.permission, *spec.additional_permissions)
        if any(item not in runtime.tenant.permission_codes for item in required_permissions):
            raise AppError("无权使用该查询工具", code=40372, status_code=403)
        if not runtime.access_token:
            raise AppError("当前令牌不能访问下游服务", code=40373, status_code=403)
        if spec.source == "ERP" and not runtime.erp_audience_authorized:
            raise AppError("当前令牌不能代表用户访问 ERP", code=40373, status_code=403)
        if spec.source == "KNOWLEDGE" and not runtime.knowledge_audience_authorized:
            raise AppError("当前令牌不能代表用户访问 Knowledge", code=40374, status_code=403)
        call_limit = runtime.max_calls_override or settings.tool_max_calls
        if runtime.calls >= call_limit:
            raise AppError("工具调用次数已达上限", code=42972, status_code=429)
        if runtime.shared_calls is not None and runtime.global_call_limit is not None:
            if runtime.shared_calls[0] >= runtime.global_call_limit:
                raise AppError("多 Agent 工具总调用次数已达上限", code=42979, status_code=429)
            runtime.shared_calls[0] += 1
        if time.monotonic() - runtime.started_at >= settings.tool_total_timeout_seconds:
            raise AppError("工具执行总时限已到", code=50472, status_code=504)
        try:
            raw_args = json.loads(call.arguments or "{}")
            if not isinstance(raw_args, dict):
                raise ValueError
            args = spec.args_model.model_validate(raw_args)
        except (json.JSONDecodeError, ValueError, ValidationError) as exc:
            raise AppError("工具参数无效", code=40071, status_code=400) from exc
        runtime.calls += 1
        started = time.monotonic()
        remaining = settings.tool_total_timeout_seconds - (started - runtime.started_at)
        try:
            async with asyncio.timeout(max(0.01, remaining)):
                if call.name == "analyze_inventory_coverage":
                    result = await self._analyze_inventory_coverage(args, runtime)
                elif call.name == "list_knowledge_bases":
                    result = await self._list_knowledge_bases(args, runtime)
                elif spec.source == "KNOWLEDGE":
                    result = await self._search_knowledge(args, runtime)
                else:
                    result = await spec.execute(
                        self.client,
                        args,
                        access_token=runtime.access_token,
                        tenant_id=runtime.tenant.tenant_id,
                        request_id=runtime.request_id,
                    )
        except TimeoutError as exc:
            raise AppError("工具执行超时", code=50472, status_code=504) from exc
        evidences = self._build_evidence(spec.source, call, result, runtime)
        runtime.evidences.extend(evidences)
        serialized = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
        truncated = len(serialized) > settings.tool_max_result_chars
        if truncated:
            serialized = serialized[: settings.tool_max_result_chars]
        content = (
            f'<untrusted_{spec.source.lower()}_tool_result queried_at="{datetime.now(UTC).isoformat()}">\n'
            + serialized
            + f"\n</untrusted_{spec.source.lower()}_tool_result>"
        )
        return ToolExecutionResult(
            content=content,
            event={
                "tool_call_id": call.id,
                "name": call.name,
                "source": spec.source,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "truncated": truncated,
                "evidence_count": len(evidences),
            },
            evidences=tuple(evidences),
        )

    async def _execute_proposal(
        self, call: ModelToolCall, runtime: ToolRuntime
    ) -> ToolExecutionResult:
        """Proposal 工具只操作 Copilot 草稿并调用白名单 Preview，不具备 ERP 写能力。"""
        if runtime.proposal_service is None or runtime.conversation_id is None:
            raise AppError("当前对话不能创建业务草稿", code=40076, status_code=400)
        if runtime.calls >= settings.tool_max_calls:
            raise AppError("工具调用次数已达上限", code=42972, status_code=429)
        try:
            raw = json.loads(call.arguments or "{}")
        except json.JSONDecodeError as exc:
            raise AppError("Proposal 工具参数无效", code=40071, status_code=400) from exc
        runtime.calls += 1
        started = time.monotonic()
        try:
            if call.name == "propose_action":
                args = ProposeActionArgs.model_validate(raw)
                proposal = await runtime.proposal_service.create(
                    ActionProposalCreate(
                        conversation_id=runtime.conversation_id,
                        source_message_id=runtime.source_message_id,
                        idempotency_key=f"agent:{runtime.source_message_id}:{call.id}"[:128],
                        action=args.action,
                    )
                )
                event_name = "proposal_created"
                if proposal.status == "DRAFT":
                    proposal = await runtime.proposal_service.validate(
                        proposal.id, proposal.current_revision
                    )
                    event_name = "proposal_validation"
            else:
                args = ValidateActionProposalArgs.model_validate(raw)
                proposal = await runtime.proposal_service.validate(
                    args.proposal_id, args.expected_revision
                )
                event_name = "proposal_validation"
        except ValidationError as exc:
            raise AppError("Proposal 工具参数无效", code=40071, status_code=400) from exc
        safe = {
            "proposal_id": proposal.id,
            "revision": proposal.current_revision,
            "action_type": proposal.action_type,
            "status": proposal.status,
            "missing_fields": (proposal.validation.missing_fields if proposal.validation else []),
            "validation_status": proposal.validation.status if proposal.validation else None,
        }
        content = (
            "<trusted_proposal_result>"
            + json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
            + "</trusted_proposal_result>"
        )
        return ToolExecutionResult(
            content=content,
            event={
                "tool_call_id": call.id,
                "name": call.name,
                "source": "PROPOSAL",
                "duration_ms": round((time.monotonic() - started) * 1000),
                "proposal_event": event_name,
                **safe,
            },
        )

    async def _search_knowledge(self, args: Any, runtime: ToolRuntime) -> dict[str, Any]:
        """调用 Knowledge 既有混合检索；授权知识库 ID 仍由 Knowledge 服务复核。"""
        if self.knowledge_client is None:
            raise AppError("Knowledge 工具未配置", code=50374, status_code=503)
        data = await self.knowledge_client.search(
            args.model_dump(mode="json", exclude_none=True),
            access_token=runtime.access_token,
            tenant_id=runtime.tenant.tenant_id,
            request_id=runtime.request_id,
        )
        items = data.get("items")
        if not isinstance(items, list):
            raise AppError("Knowledge 返回了无效检索结果", code=50275, status_code=502)
        safe_items = []
        for item in items[: settings.knowledge_top_k_max]:
            if not isinstance(item, dict):
                continue
            safe = {
                key: item.get(key)
                for key in (
                    "chunk_id",
                    "document_id",
                    "knowledge_base_id",
                    "filename",
                    "content",
                    "page_no",
                    "heading",
                    "chunk_index",
                    "version",
                    "final_rank",
                    "vector_score",
                    "keyword_score",
                    "rrf_score",
                    "rerank_score",
                )
                if key in item
            }
            safe["content"] = str(safe.get("content") or "")[
                : settings.knowledge_evidence_excerpt_chars
            ]
            safe_items.append(safe)
        return {
            "items": safe_items,
            "strategy": data.get("strategy"),
            "rerank_applied": data.get("rerank_applied"),
            "rerank_degraded": data.get("rerank_degraded"),
        }

    async def _list_knowledge_bases(self, args: Any, runtime: ToolRuntime) -> dict[str, Any]:
        """仅返回 Knowledge 已按当前主体过滤后的知识库标识和名称。"""
        if self.knowledge_client is None:
            raise AppError("Knowledge 工具未配置", code=50374, status_code=503)
        data = await self.knowledge_client.list_bases(
            args.model_dump(mode="json", exclude_none=True) | {"status": "ACTIVE"},
            access_token=runtime.access_token,
            tenant_id=runtime.tenant.tenant_id,
            request_id=runtime.request_id,
        )
        items = data.get("items")
        if not isinstance(items, list):
            raise AppError("Knowledge 返回了无效知识库列表", code=50275, status_code=502)
        return {
            "items": [
                {key: item.get(key) for key in ("id", "name", "description") if key in item}
                for item in items[:20]
                if isinstance(item, dict)
            ],
            "total": data.get("total"),
        }

    async def _analyze_inventory_coverage(self, args: Any, runtime: ToolRuntime) -> dict[str, Any]:
        """以 ERP 精确 SKU 销量和实时库存执行确定性覆盖天数公式。"""
        values = args.model_dump(mode="json", exclude_none=True)
        common = {
            "access_token": runtime.access_token,
            "tenant_id": runtime.tenant.tenant_id,
            "request_id": runtime.request_id,
        }
        sales = await self.client.get(
            "/api/v1/analytics/sales/sku",
            params=values,
            **common,
        )
        if sales is None:
            raise AppError("目标 SKU 不存在", code=40470, status_code=404)
        inventory_params = {
            "sku_code": values["sku_code"],
            "page": 1,
            "page_size": settings.tool_max_page_size,
        }
        if values.get("warehouse_id") is not None:
            inventory_params["warehouse_id"] = values["warehouse_id"]
        inventory = await self.client.get(
            "/api/v1/inventory",
            params=inventory_params,
            **common,
        )
        if not isinstance(sales, dict) or not isinstance(inventory, dict):
            raise AppError("ERP 返回了无效分析数据", code=50272, status_code=502)
        rows = inventory.get("items")
        if not isinstance(rows, list) or int(inventory.get("total") or 0) > len(rows):
            raise AppError("库存记录过多，请指定仓库后重试", code=40075, status_code=400)
        try:
            available = sum(
                Decimal(str(item.get("available_quantity") or 0))
                for item in rows
                if isinstance(item, dict)
            )
            period_days = Decimal(str(sales.get("period_days") or 0))
            sales_quantity = Decimal(str(sales.get("sales_quantity") or 0))
            if period_days <= 0:
                raise InvalidOperation
            average = sales_quantity / period_days
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise AppError("ERP 返回了无效分析数据", code=50272, status_code=502) from exc
        coverage = None if average <= 0 else available / average
        return {
            "sku_id": sales.get("sku_id"),
            "sku_code": sales.get("sku_code"),
            "sku_name": sales.get("sku_name"),
            "warehouse_id": values.get("warehouse_id"),
            "start_date": sales.get("start_date"),
            "end_date": sales.get("end_date"),
            "period_days": sales.get("period_days"),
            "sales_quantity": sales.get("sales_quantity"),
            "order_count": sales.get("order_count"),
            "average_daily_sales": float(average),
            "available_quantity": float(available),
            "coverage_days": round(float(coverage), 2) if coverage is not None else None,
            "formula": "available_quantity / average_daily_sales",
            "calculated_at": datetime.now(UTC).isoformat(),
        }

    @staticmethod
    def _build_evidence(
        source: str,
        call: ModelToolCall,
        result: Any,
        runtime: ToolRuntime,
    ) -> list[dict[str, Any]]:
        """从已净化的工具结果生成稳定引用，不接受模型自行声明来源。"""
        now = datetime.now(UTC).isoformat()
        rows = result.get("items", []) if isinstance(result, dict) else []
        if source == "KNOWLEDGE":
            evidences = []
            for row in rows:
                if not isinstance(row, dict) or not row.get("chunk_id"):
                    continue
                number = (
                    sum(item.get("source_type") == "KNOWLEDGE" for item in runtime.evidences)
                    + len(evidences)
                    + 1
                )
                citation_id = f"K{number}"
                row["citation_id"] = citation_id
                evidences.append(
                    {
                        "citation_id": citation_id,
                        "source_type": source,
                        "tool_call_id": call.id,
                        "resource_type": "knowledge_chunk",
                        "resource_id": str(row.get("chunk_id")),
                        "knowledge_base_id": row.get("knowledge_base_id"),
                        "document_id": row.get("document_id"),
                        "chunk_id": row.get("chunk_id"),
                        "title": str(row.get("filename") or "知识库文档")[:255],
                        "excerpt": str(row.get("content") or "")[
                            : settings.knowledge_evidence_excerpt_chars
                        ],
                        "source_version": row.get("version"),
                        "metadata": {
                            key: row.get(key)
                            for key in (
                                "page_no",
                                "heading",
                                "chunk_index",
                                "final_rank",
                                "vector_score",
                                "keyword_score",
                                "rrf_score",
                                "rerank_score",
                            )
                            if row.get(key) is not None
                        },
                        "observed_at": now,
                    }
                )
            return evidences
        number = sum(item.get("source_type") == "ERP" for item in runtime.evidences) + 1
        citation_id = f"E{number}"
        try:
            call_args = json.loads(call.arguments or "{}")
        except json.JSONDecodeError:
            call_args = {}
        resource_id = next(
            (
                str(call_args[key])
                for key in ("sku_code", "order_id", "product_id", "warehouse_id", "after_sale_id")
                if call_args.get(key) is not None
            ),
            None,
        )
        return [
            {
                "citation_id": citation_id,
                "source_type": source,
                "tool_call_id": call.id,
                "resource_type": call.name,
                "resource_id": resource_id,
                "title": f"ERP 查询：{call.name}",
                "excerpt": json.dumps(result, ensure_ascii=False, separators=(",", ":"))[
                    : settings.knowledge_evidence_excerpt_chars
                ],
                "source_version": None,
                "metadata": {},
                "observed_at": now,
            }
        ]
