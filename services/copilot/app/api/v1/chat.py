from __future__ import annotations

import asyncio
import json
from typing import cast
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.types import ModelMessage
from app.api.deps import CopilotContext, DbSession, WorkflowDep
from app.core.config import settings
from app.core.exceptions import AppError
from app.erp.client import get_erp_client
from app.graph.workflow import AgentRuntime
from app.mcp.gateway import McpGateway
from app.schemas.chat import ChatRequest, ChatResponse, TokenUsageOut
from app.schemas.common import ApiResponse, ok
from app.services.action_proposals import ActionProposalService
from app.services.chat import ChatService
from app.services.persistent_chat import PersistentChatService
from app.services.quotas import (
    RuntimeGovernance,
    enforce_runtime_governance,
    reserve_chat_quota,
    usage_tokens,
)
from app.skills.chat import ChatSkillSession, prepare_chat_skill, skill_timeout
from app.skills.orchestration import MultiSkillChatSession
from app.skills.pending import PendingSkillPrompt
from app.tools.executor import ToolRuntime

ActiveSkillSession = ChatSkillSession | MultiSkillChatSession

router = APIRouter(prefix="/chat", tags=["copilot-chat"])


def _messages(payload: ChatRequest) -> list[ModelMessage]:
    return [{"role": item.role, "content": item.content} for item in payload.messages]


def _active_skill(session: object) -> ActiveSkillSession | None:
    return session if isinstance(session, (ChatSkillSession, MultiSkillChatSession)) else None


def _skill_fail_message(session: ActiveSkillSession) -> str:
    if isinstance(session, ChatSkillSession):
        return session.row.safe_error or "模型生成失败"
    return session.plan.safe_error or "模型生成失败"


def _skill_still_running(session: ActiveSkillSession) -> bool:
    if isinstance(session, ChatSkillSession):
        return session.row.status == "RUNNING"
    return session.plan.status == "RUNNING"


def _event_data(event: dict) -> dict:
    raw = event.get("data")
    return raw if isinstance(raw, dict) else {}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _runtime(
    request: Request,
    context: CopilotContext,
    db: DbSession,
    *,
    conversation_id: int | None = None,
    source_message_id: int | None = None,
    governance: RuntimeGovernance | None = None,
    mcp_gateway: McpGateway | None = None,
) -> AgentRuntime:
    audiences = frozenset(getattr(request.state, "jwt_audiences", ()))
    access_token = str(getattr(request.state, "access_token", ""))
    request_id = str(getattr(request.state, "request_id", ""))
    proposal_service = None
    if conversation_id is not None:
        proposal_service = ActionProposalService(
            cast(AsyncSession, db),
            context,
            erp_client=get_erp_client(),
            access_token=access_token,
            request_id=request_id,
        )
    return AgentRuntime(
        tools=ToolRuntime(
            tenant=context,
            access_token=access_token,
            erp_audience_authorized=settings.erp_jwt_audience in audiences,
            knowledge_audience_authorized=settings.knowledge_jwt_audience in audiences,
            request_id=request_id,
            proposal_service=proposal_service,
            conversation_id=conversation_id,
            source_message_id=source_message_id,
            allowed_tools=governance.allowed_tools if governance else None,
            max_calls_override=governance.max_tool_calls if governance else None,
            global_call_limit=governance.max_tool_calls if governance else None,
            mcp_gateway=mcp_gateway,
        ),
        allow_multi_agent=governance.allow_multi_agent if governance else True,
    )


@router.post("", response_model=ApiResponse[ChatResponse], summary="非流式对话")
async def chat(
    payload: ChatRequest,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> ApiResponse[ChatResponse]:
    governance = await enforce_runtime_governance(cast(AsyncSession, db), context.tenant_id, "CHAT")
    reservation = await reserve_chat_quota(
        cast(AsyncSession, db), context.tenant_id, _estimated_tokens(payload)
    )
    mcp_gateway = await McpGateway.load(
        cast(AsyncSession, db),
        context,
        allowed_tools=governance.allowed_tools,
        request_id=str(getattr(request.state, "request_id", "")),
    )
    usage = None
    try:
        if payload.conversation_id is not None:
            service = PersistentChatService(cast(AsyncSession, db), context, workflow)
            turn = await service.prepare(
                payload.conversation_id,
                payload.message or "",
                payload.client_request_id or "",
                str(getattr(request.state, "request_id", "") or uuid4().hex),
            )
            if turn.duplicate_answer is not None:
                await reservation.release()
            runtime = _runtime(
                request,
                context,
                db,
                conversation_id=turn.conversation_id,
                source_message_id=turn.message_id,
                governance=governance,
                mcp_gateway=mcp_gateway,
            )
            skill_session = None
            if turn.duplicate_answer is None:
                try:
                    skill_session = await prepare_chat_skill(
                        cast(AsyncSession, db),
                        context,
                        payload.message or "",
                        turn.request_id,
                        runtime,
                        conversation_id=turn.conversation_id,
                        message_id=turn.message_id,
                        skill_mode=payload.skill_mode or "AUTO",
                        explicit_skill_key=payload.skill_key,
                        selector_adapter=workflow.adapter,
                    )
                except AppError as exc:
                    await service.fail_before_run(turn, exc.code)
                    raise
            if isinstance(skill_session, PendingSkillPrompt):
                await service.complete_without_run(turn, skill_session.answer)
                await reservation.release()
                return ok(
                    ChatResponse(
                        answer=skill_session.answer,
                        model=settings.chat_model,
                        conversation_id=turn.conversation_id,
                        message_id=turn.message_id,
                        request_id=turn.request_id,
                        skill=skill_session.public_data,
                    )
                )
            answer = ""
            async for event in service.events(
                turn,
                runtime,
                lambda: _false(),
                skill_session,
            ):
                if event["event"] == "done":
                    answer = str(event["data"].get("answer") or "")
                    usage = event["data"].get("usage")
            response = ChatResponse(
                answer=answer,
                model=settings.chat_model,
                usage=TokenUsageOut.model_validate(usage) if isinstance(usage, dict) else None,
                conversation_id=turn.conversation_id,
                message_id=turn.message_id,
                request_id=turn.request_id,
                skill=skill_session.public_data if skill_session is not None else None,
            )
        else:
            messages = _messages(payload)
            runtime = _runtime(
                request,
                context,
                db,
                governance=governance,
                mcp_gateway=mcp_gateway,
            )
            skill_session = await prepare_chat_skill(
                cast(AsyncSession, db),
                context,
                str(messages[-1]["content"]),
                str(getattr(request.state, "request_id", "") or uuid4().hex),
                runtime,
                conversation_id=None,
                message_id=None,
                skill_mode=payload.skill_mode or "AUTO",
                explicit_skill_key=payload.skill_key,
                selector_adapter=workflow.adapter,
            )
            if isinstance(skill_session, PendingSkillPrompt):
                raise AppError("无会话模式不支持多轮参数补全", code=42293, status_code=422)
            try:
                async with skill_timeout(skill_session):
                    answer, usage = await ChatService(workflow).complete(
                        skill_session.messages(messages) if skill_session is not None else messages,
                        context=runtime,
                    )
                if skill_session is not None:
                    await skill_session.complete(answer, usage, runtime)
            except BaseException as exc:
                if skill_session is not None:
                    await skill_session.fail(exc, runtime)
                raise
            response = ChatResponse(
                answer=answer,
                model=settings.chat_model,
                usage=TokenUsageOut.model_validate(usage) if usage is not None else None,
                skill=skill_session.public_data if skill_session is not None else None,
            )
        await reservation.settle(usage_tokens(usage))
        return ok(response)
    except BaseException:
        await reservation.cancel()
        raise


@router.post("/stream", summary="SSE 流式对话")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    context: CopilotContext,
    workflow: WorkflowDep,
    db: DbSession,
) -> StreamingResponse:
    stream_request_id = str(getattr(request.state, "request_id", "") or uuid4().hex)
    governance = await enforce_runtime_governance(cast(AsyncSession, db), context.tenant_id, "CHAT")
    reservation = await reserve_chat_quota(
        cast(AsyncSession, db), context.tenant_id, _estimated_tokens(payload)
    )
    mcp_gateway = await McpGateway.load(
        cast(AsyncSession, db),
        context,
        allowed_tools=governance.allowed_tools,
        request_id=stream_request_id,
    )

    async def event_stream():
        persistent_turn = None
        persistent_service = None
        skill_session = None
        runtime = None
        buffered_skill_answer = ""
        final_usage = None
        completed = False
        quota_released = False
        try:
            if payload.conversation_id is not None:
                service = PersistentChatService(cast(AsyncSession, db), context, workflow)
                persistent_service = service
                turn = await service.prepare(
                    payload.conversation_id,
                    payload.message or "",
                    payload.client_request_id or "",
                    stream_request_id,
                )
                if turn.duplicate_answer is not None:
                    await reservation.release()
                persistent_turn = turn
                runtime = _runtime(
                    request,
                    context,
                    db,
                    conversation_id=turn.conversation_id,
                    source_message_id=turn.message_id,
                    governance=governance,
                    mcp_gateway=mcp_gateway,
                )
                if turn.duplicate_answer is None:
                    skill_session = await prepare_chat_skill(
                        cast(AsyncSession, db),
                        context,
                        payload.message or "",
                        turn.request_id,
                        runtime,
                        conversation_id=turn.conversation_id,
                        message_id=turn.message_id,
                        skill_mode=payload.skill_mode or "AUTO",
                        explicit_skill_key=payload.skill_key,
                        selector_adapter=workflow.adapter,
                    )
                    if isinstance(skill_session, PendingSkillPrompt):
                        await service.complete_without_run(turn, skill_session.answer)
                        await reservation.release()
                        quota_released = True
                        completed = True
                        yield _sse("skill_input_required", skill_session.public_data | {"request_id": turn.request_id, "conversation_id": turn.conversation_id, "message_id": turn.message_id})
                        yield _sse("message", {"request_id": turn.request_id, "conversation_id": turn.conversation_id, "message_id": turn.message_id, "delta": skill_session.answer})
                        yield _sse("done", {"request_id": turn.request_id, "conversation_id": turn.conversation_id, "message_id": turn.message_id, "answer": skill_session.answer})
                        return
                events = service.events(
                    turn,
                    runtime,
                    request.is_disconnected,
                    _active_skill(skill_session),
                )
            else:
                messages = _messages(payload)
                runtime = _runtime(
                    request,
                    context,
                    db,
                    governance=governance,
                    mcp_gateway=mcp_gateway,
                )
                skill_session = await prepare_chat_skill(
                    cast(AsyncSession, db),
                    context,
                    str(messages[-1]["content"]),
                    stream_request_id,
                    runtime,
                    conversation_id=None,
                    message_id=None,
                    skill_mode=payload.skill_mode or "AUTO",
                    explicit_skill_key=payload.skill_key,
                    selector_adapter=workflow.adapter,
                )
                if isinstance(skill_session, PendingSkillPrompt):
                    raise AppError("无会话模式不支持多轮参数补全", code=42293, status_code=422)
                events = ChatService(workflow).stream_events(
                    skill_session.messages(messages) if skill_session is not None else messages,
                    disconnected=request.is_disconnected,
                    context=runtime,
                )
                if skill_session is not None:
                    for event in skill_session.lifecycle_events():
                        yield _sse(event["event"], event["data"] | {"request_id": stream_request_id})
            async with skill_timeout(
                _active_skill(skill_session) if payload.conversation_id is None else None
            ):
                async for event in events:
                    name = str(event.get("event") or "message")
                    data = _event_data(event)
                    if (
                        payload.conversation_id is None
                        and skill_session is not None
                        and name == "message"
                    ):
                        buffered_skill_answer += str(data.get("delta") or "")
                        continue
                    if name == "done":
                        final_usage = data.get("usage")
                        if payload.conversation_id is None and skill_session is not None:
                            await skill_session.complete(
                                str(data.get("answer") or ""), final_usage, runtime
                            )
                            yield _sse(
                                "skill_done",
                                skill_session.public_data
                                | {"request_id": stream_request_id, "status": "SUCCEEDED"},
                            )
                            yield _sse(
                                "message",
                                {
                                    "request_id": stream_request_id,
                                    "delta": str(data.get("answer") or buffered_skill_answer),
                                },
                            )
                        completed = True
                    data.setdefault("request_id", stream_request_id)
                    yield _sse(name, data)
        except AppError as exc:
            running_skill = _active_skill(skill_session)
            if persistent_turn is not None and persistent_service is not None:
                await persistent_service.fail_before_run(persistent_turn, exc.code)
            if payload.conversation_id is None and running_skill is not None and runtime is not None:
                await running_skill.fail(exc, runtime)
                yield _sse(
                    "skill_error",
                    running_skill.public_data
                    | {"request_id": stream_request_id, "status": "FAILED", "message": exc.message},
                )
            ids = (
                {
                    "request_id": persistent_turn.request_id,
                    "conversation_id": persistent_turn.conversation_id,
                    "message_id": persistent_turn.message_id,
                }
                if persistent_turn is not None
                else {}
            )
            yield _sse(
                "error",
                {"code": exc.code, "message": exc.message, "request_id": stream_request_id} | ids,
            )
        except Exception as exc:
            running_skill = _active_skill(skill_session)
            if persistent_turn is not None and persistent_service is not None:
                await persistent_service.fail_before_run(persistent_turn, 50268)
            if payload.conversation_id is None and running_skill is not None and runtime is not None:
                await running_skill.fail(exc, runtime)
                yield _sse(
                    "skill_error",
                    running_skill.public_data
                    | {
                        "request_id": stream_request_id,
                        "status": "FAILED",
                        "message": _skill_fail_message(running_skill),
                    },
                )
            ids = (
                {
                    "request_id": persistent_turn.request_id,
                    "conversation_id": persistent_turn.conversation_id,
                    "message_id": persistent_turn.message_id,
                }
                if persistent_turn is not None
                else {}
            )
            yield _sse(
                "error",
                {"code": 50268, "message": "模型生成失败", "request_id": stream_request_id} | ids,
            )
        finally:
            running_skill = _active_skill(skill_session)
            if (
                not completed
                and payload.conversation_id is None
                and running_skill is not None
                and runtime is not None
                and _skill_still_running(running_skill)
            ):
                await running_skill.fail(asyncio.CancelledError(), runtime)
            if completed and not quota_released:
                await reservation.settle(usage_tokens(final_usage))
            elif not completed and not quota_released:
                await reservation.cancel()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _false() -> bool:
    return False


def _estimated_tokens(payload: ChatRequest) -> int:
    text_size = len(payload.message or "") + sum(len(item.content) for item in payload.messages)
    return max(1, (text_size + 2) // 3) + settings.chat_max_output_tokens
