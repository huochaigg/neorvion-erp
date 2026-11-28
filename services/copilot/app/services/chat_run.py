"""Chat Run 进程内执行器：SSE 订阅与 Agent 执行分离。

执行权以 PostgreSQL AgentRun.worker_instance_id / heartbeat 为准；
Redis 仅缓存近期事件以便断线补发。进程退出后不得假设能从 Token 精确 Resume。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.tenant import TenantContext
from app.models.conversation import MessageStatus
from app.tasks.queue import async_redis


def open_run_session(tenant_id: int):
    """后台执行使用独立租户会话；测试可替换为内存 Session。"""
    from app.db.session import open_tenant_session

    return open_tenant_session(tenant_id)

logger = logging.getLogger(__name__)

WORKER_INSTANCE_ID = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"

_TERMINAL_EVENTS = frozenset({"done", "error"})


def _lease_key(tenant_id: int, message_id: int) -> str:
    return f"copilot:chat-lease:{tenant_id}:{message_id}"


def _stream_key(tenant_id: int, message_id: int) -> str:
    return f"copilot:chat-events:{tenant_id}:{message_id}"


def _cancel_key(tenant_id: int, message_id: int) -> str:
    return f"copilot:chat-cancel:{tenant_id}:{message_id}"


_start_lock = asyncio.Lock()


@dataclass
class ChatLiveRun:
    """单个助手消息对应的本进程执行会话。"""

    tenant_id: int
    user_id: int
    conversation_id: int
    message_id: int
    request_id: str
    cancel: asyncio.Event = field(default_factory=asyncio.Event)
    seq: int = 0
    log: list[tuple[int, str, dict]] = field(default_factory=list)
    waiters: list[asyncio.Queue] = field(default_factory=list)
    task: asyncio.Task | None = None
    closed: bool = False
    last_progress_at: float = field(default_factory=time.monotonic)

    async def cancel_requested(self) -> bool:
        return self.cancel.is_set()

    def publish(self, event: str, data: dict) -> int:
        self.seq += 1
        payload = dict(data)
        payload["event_id"] = self.seq
        payload["sequence"] = self.seq
        payload["run_id"] = self.message_id
        item = (self.seq, event, payload)
        self.log.append(item)
        if len(self.log) > settings.chat_event_log_max:
            self.log = self.log[-settings.chat_event_log_max :]
        if event not in {"ping", "heartbeat"}:
            self.last_progress_at = time.monotonic()
        for waiter in list(self.waiters):
            try:
                waiter.put_nowait(item)
            except asyncio.QueueFull:
                pass
        return self.seq

    def close(self) -> None:
        self.closed = True
        for waiter in list(self.waiters):
            try:
                waiter.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self.waiters.clear()


class ChatRunHub:
    def __init__(self) -> None:
        self._runs: dict[tuple[int, int], ChatLiveRun] = {}

    def get(self, tenant_id: int, message_id: int) -> ChatLiveRun | None:
        return self._runs.get((tenant_id, message_id))

    def register(self, run: ChatLiveRun) -> ChatLiveRun:
        self._runs[(run.tenant_id, run.message_id)] = run
        return run

    def drop(self, tenant_id: int, message_id: int) -> None:
        self._runs.pop((tenant_id, message_id), None)

    def is_live(self, tenant_id: int, message_id: int) -> bool:
        run = self.get(tenant_id, message_id)
        if run is None or run.closed:
            return False
        if run.task is None:
            return True
        return not run.task.done()


hub = ChatRunHub()


async def touch_lease(run: ChatLiveRun, agent_run_id: int | None = None) -> None:
    """刷新 Redis 租约；失败时不影响 PostgreSQL 心跳路径。"""
    ttl = max(30, settings.chat_lease_seconds)
    body = json.dumps(
        {
            "instance_id": WORKER_INSTANCE_ID,
            "request_id": run.request_id,
            "seq": run.seq,
            "agent_run_id": agent_run_id,
            "heartbeat_at": datetime.now(UTC).isoformat(),
        }
    )
    try:
        await async_redis().set(_lease_key(run.tenant_id, run.message_id), body, ex=ttl)
    except (RedisError, RuntimeError):
        logger.warning(
            "chat lease redis unavailable tenant_id=%s message_id=%s",
            run.tenant_id,
            run.message_id,
        )


async def lease_alive(tenant_id: int, message_id: int) -> bool:
    try:
        value = await async_redis().get(_lease_key(tenant_id, message_id))
    except (RedisError, RuntimeError):
        return False
    return bool(value)


async def append_event_stream(run: ChatLiveRun, seq: int, event: str, data: dict) -> None:
    try:
        await async_redis().xadd(
            _stream_key(run.tenant_id, run.message_id),
            {"seq": str(seq), "event": event, "data": json.dumps(data, ensure_ascii=False)},
            maxlen=settings.chat_event_log_max,
            approximate=True,
        )
        await async_redis().expire(_stream_key(run.tenant_id, run.message_id), max(300, settings.chat_lease_seconds * 20))
    except (RedisError, RuntimeError):
        return


async def replay_redis_events(
    tenant_id: int, message_id: int, after: int
) -> tuple[list[tuple[int, str, dict]], str]:
    last_id = "0-0"
    try:
        rows = await async_redis().xrange(_stream_key(tenant_id, message_id), min="-", max="+")
    except (RedisError, RuntimeError):
        return [], last_id
    items: list[tuple[int, str, dict]] = []
    for redis_id, fields in rows or []:
        last_id = str(redis_id)
        try:
            seq = int(fields.get("seq") or 0)
            event = str(fields.get("event") or "message")
            data = json.loads(fields.get("data") or "{}")
        except (TypeError, ValueError):
            continue
        if seq > after:
            items.append((seq, event, data if isinstance(data, dict) else {}))
    return items, last_id


async def cancel_flag_set(tenant_id: int, message_id: int) -> None:
    try:
        await async_redis().set(
            _cancel_key(tenant_id, message_id),
            "1",
            ex=max(300, settings.chat_lease_seconds * 20),
        )
    except (RedisError, RuntimeError):
        return


async def cancel_flag_raised(tenant_id: int, message_id: int) -> bool:
    try:
        return bool(await async_redis().get(_cancel_key(tenant_id, message_id)))
    except (RedisError, RuntimeError):
        return False


def _ping(message_id: int, seq: int) -> tuple[int, str, dict]:
    return seq, "ping", {
        "sequence": seq,
        "run_id": message_id,
        "debug_execution": settings.debug_execution_enabled(),
    }


async def _follow_live(
    live: ChatLiveRun,
    after: int,
    disconnected: Callable[[], Any] | None,
) -> AsyncIterator[tuple[int, str, dict]]:
    queue: asyncio.Queue = asyncio.Queue(maxsize=512)
    live.waiters.append(queue)
    try:
        while True:
            if disconnected is not None and await disconnected():
                return
            try:
                item = await asyncio.wait_for(queue.get(), timeout=settings.chat_heartbeat_seconds)
            except TimeoutError:
                yield _ping(live.message_id, live.seq)
                continue
            if item is None:
                return
            seq, event, data = item
            if seq > after:
                yield seq, event, data
            if event in _TERMINAL_EVENTS:
                return
    finally:
        if queue in live.waiters:
            live.waiters.remove(queue)


async def subscribe(
    tenant_id: int,
    user_id: int,
    message_id: int,
    after: int = 0,
    *,
    disconnected: Callable[[], Any] | None = None,
) -> AsyncIterator[tuple[int, str, dict]]:
    """按 sequence 补发后再接直播。HTTP 断开只结束本订阅，不取消 Run。"""
    del user_id
    last_seq = after
    live = hub.get(tenant_id, message_id)
    if live is not None:
        for seq, event, data in list(live.log):
            if seq <= last_seq:
                continue
            last_seq = seq
            yield seq, event, data
            if event in _TERMINAL_EVENTS:
                return
        if live.closed:
            return
        async for item in _follow_live(live, last_seq, disconnected):
            yield item
        return

    replayed, last_id = await replay_redis_events(tenant_id, message_id, after)
    for seq, event, data in replayed:
        last_seq = seq
        yield seq, event, data
        if event in _TERMINAL_EVENTS:
            return

    live = hub.get(tenant_id, message_id)
    if live is not None and not live.closed:
        for seq, event, data in list(live.log):
            if seq <= last_seq:
                continue
            last_seq = seq
            yield seq, event, data
            if event in _TERMINAL_EVENTS:
                return
        async for item in _follow_live(live, last_seq, disconnected):
            yield item
        return

    stream_key = _stream_key(tenant_id, message_id)
    empty_reads = 0
    while True:
        if disconnected is not None and await disconnected():
            return
        live = hub.get(tenant_id, message_id)
        if live is not None and not live.closed:
            for seq, event, data in list(live.log):
                if seq <= last_seq:
                    continue
                last_seq = seq
                yield seq, event, data
                if event in _TERMINAL_EVENTS:
                    return
            async for item in _follow_live(live, last_seq, disconnected):
                yield item
            return
        try:
            result = await async_redis().xread(
                {stream_key: last_id},
                block=int(settings.chat_heartbeat_seconds * 1000),
                count=100,
            )
        except (RedisError, RuntimeError):
            yield _ping(message_id, last_seq)
            await asyncio.sleep(settings.chat_heartbeat_seconds)
            empty_reads += 1
            if empty_reads >= 3 and not await lease_alive(tenant_id, message_id):
                return
            continue
        if not result:
            yield _ping(message_id, last_seq)
            if not await lease_alive(tenant_id, message_id) and hub.get(tenant_id, message_id) is None:
                return
            continue
        empty_reads = 0
        for _key, entries in result:
            for redis_id, fields in entries:
                last_id = str(redis_id)
                try:
                    seq = int(fields.get("seq") or 0)
                    event = str(fields.get("event") or "message")
                    data = json.loads(fields.get("data") or "{}")
                except (TypeError, ValueError):
                    continue
                if seq <= last_seq:
                    continue
                last_seq = seq
                yield seq, event, data if isinstance(data, dict) else {}
                if event in _TERMINAL_EVENTS:
                    return


async def request_cancel(tenant_id: int, message_id: int) -> bool:
    await cancel_flag_set(tenant_id, message_id)
    live = hub.get(tenant_id, message_id)
    if live is not None:
        live.cancel.set()
        return True
    return await lease_alive(tenant_id, message_id)


@dataclass(frozen=True, slots=True)
class ChatRunAuth:
    """仅存在于当前进程内存，禁止写入 Redis 任务参数。"""

    context: TenantContext
    access_token: str
    jwt_audiences: frozenset[str]
    request_id: str
    skill_mode: str
    skill_key: str | None
    user_message: str


async def start_persistent_run(
    *,
    turn: Any,
    auth: ChatRunAuth,
    reservation: Any | None = None,
    skill_session: Any | None = None,
    skip_intent: bool = False,
    intent_resolution: Any | None = None,
    bound_runtime: Any | None = None,
    workflow: Any | None = None,
) -> ChatLiveRun:
    """在独立租户会话中执行 Intent/Skill/Graph；与当前 HTTP 生成器解耦。"""
    async with _start_lock:
        existing = hub.get(auth.context.tenant_id, turn.message_id)
        if existing is not None and hub.is_live(auth.context.tenant_id, turn.message_id):
            return existing
        if (
            existing is not None
            and existing.closed
            and existing.request_id == turn.request_id
        ):
            return existing
        if existing is not None:
            hub.drop(auth.context.tenant_id, turn.message_id)
        live = ChatLiveRun(
            tenant_id=auth.context.tenant_id,
            user_id=auth.context.user_id,
            conversation_id=turn.conversation_id,
            message_id=turn.message_id,
            request_id=turn.request_id,
        )
        hub.register(live)
        logger.info(
            "RUN_STARTED tenant_id=%s message_id=%s request_id=%s instance=%s",
            live.tenant_id,
            live.message_id,
            turn.request_id,
            WORKER_INSTANCE_ID,
        )
        if settings.is_test:
            await _execute(
                live,
                turn,
                auth,
                reservation,
                skill_session,
                skip_intent,
                intent_resolution,
                bound_runtime,
                workflow,
            )
        else:
            live.task = asyncio.create_task(
                _execute(
                    live,
                    turn,
                    auth,
                    reservation,
                    skill_session,
                    skip_intent,
                    intent_resolution,
                    None,
                    workflow,
                ),
                name=f"chat-run-{turn.message_id}",
            )
        return live


async def _execute(
    live: ChatLiveRun,
    turn: Any,
    auth: ChatRunAuth,
    reservation: Any | None,
    prepared_skill: Any | None = None,
    skip_intent: bool = False,
    intent_resolution: Any | None = None,
    bound_runtime: Any | None = None,
    workflow: Any | None = None,
) -> None:
    from app.api.deps import get_workflow
    from app.api.v1.chat import McpGateway, _active_skill, _prepare_with_intent, _runtime_from_auth
    from app.core.exceptions import AppError
    from app.intent.integration import IntentClarification, apply_resolution_to_runtime
    from app.models.conversation import MessageStatus
    from app.services.persistent_chat import PersistentChatService
    from app.services.quotas import enforce_runtime_governance, usage_tokens
    from app.skills.pending import PendingSkillPrompt

    session = open_run_session(auth.context.tenant_id)
    completed = False
    quota_released = reservation is None

    async def _quota(action: str, usage: Any | None = None) -> None:
        nonlocal quota_released
        if reservation is None or quota_released:
            return
        try:
            if action == "settle":
                await reservation.settle(usage_tokens(usage))
            elif action == "release":
                await reservation.release()
            else:
                await reservation.cancel()
            quota_released = True
        except Exception:
            logger.warning(
                "quota finalize failed action=%s message_id=%s",
                action,
                live.message_id,
                exc_info=True,
            )

    async def cancel_requested() -> bool:
        return live.cancel.is_set()

    try:
        workflow = workflow or get_workflow()
        service = PersistentChatService(session, auth.context, workflow)
        governance = await enforce_runtime_governance(session, auth.context.tenant_id, "CHAT")
        mcp_gateway = await McpGateway.load(
            session,
            auth.context,
            allowed_tools=governance.allowed_tools,
            request_id=auth.request_id,
        )
        runtime = bound_runtime or _runtime_from_auth(
            auth,
            session,
            conversation_id=turn.conversation_id,
            source_message_id=turn.message_id,
            governance=governance,
            mcp_gateway=mcp_gateway,
        )
        skill_session = prepared_skill
        if skip_intent and intent_resolution is not None:
            apply_resolution_to_runtime(runtime, intent_resolution)
        if turn.duplicate_answer is None and not skip_intent:
            skill_session, intent_resolution = await _prepare_with_intent(
                session,
                auth.context,
                auth.user_message,
                turn.request_id,
                runtime,
                conversation_id=turn.conversation_id,
                message_id=turn.message_id,
                skill_mode=auth.skill_mode,
                explicit_skill_key=auth.skill_key,
                selector_adapter=workflow.adapter,
                recent_messages=[
                    {"role": str(item.get("role") or ""), "content": str(item.get("content") or "")}
                    for item in turn.history
                    if item.get("role") in {"user", "assistant"} and item.get("content")
                ],
            )
            if intent_resolution is not None and intent_resolution.public_status:
                seq = live.publish("intent_resolved", intent_resolution.public_payload() | {
                    "request_id": turn.request_id,
                    "conversation_id": turn.conversation_id,
                    "message_id": turn.message_id,
                })
                await append_event_stream(live, seq, "intent_resolved", intent_resolution.public_payload())
            if isinstance(skill_session, (PendingSkillPrompt, IntentClarification)):
                await service.complete_without_run(turn, skill_session.answer, runtime)
                event_name = (
                    "skill_input_required"
                    if isinstance(skill_session, PendingSkillPrompt)
                    else "intent_clarification"
                )
                ids = {
                    "request_id": turn.request_id,
                    "conversation_id": turn.conversation_id,
                    "message_id": turn.message_id,
                }
                for name, data in (
                    (event_name, skill_session.public_data | ids),
                    ("message", ids | {"delta": skill_session.answer}),
                    ("done", ids | {"answer": skill_session.answer}),
                ):
                    seq = live.publish(name, data)
                    await append_event_stream(live, seq, name, data)
                completed = True
                await _quota("release")
                return
        last_beat = 0.0
        async for event in service.events(turn, runtime, cancel_requested, _active_skill(skill_session)):
            name = str(event.get("event") or "message")
            data = event.get("data") if isinstance(event.get("data"), dict) else {}
            seq = live.publish(name, data)
            await append_event_stream(live, seq, name, data)
            if await cancel_flag_raised(live.tenant_id, live.message_id):
                live.cancel.set()
            now = time.monotonic()
            if now - last_beat >= settings.chat_heartbeat_seconds:
                last_beat = now
                if runtime.agent_run_id:
                    await service.repo.heartbeat_agent_run(
                        int(runtime.agent_run_id),
                        event_seq=seq,
                        progress=name not in {"ping", "heartbeat"},
                    )
                    await session.commit()
                await touch_lease(live, int(runtime.agent_run_id) if runtime.agent_run_id else None)
            if name == "done":
                completed = True
                await _quota("settle", data.get("usage"))
            if settings.execution_timeout_enabled() and (
                time.monotonic() - live.last_progress_at > settings.chat_execution_timeout_seconds
            ):
                runtime.termination_status = MessageStatus.TIMED_OUT.value
                runtime.termination_code = 50482
                raise AppError("任务执行超时", code=50482, status_code=504)
    except AppError as exc:
        if not completed:
            try:
                await service.fail_before_run(turn, exc.code)
            except Exception:
                logger.exception("fail_before_run after AppError message_id=%s", live.message_id)
        seq = live.publish(
            "error",
            {
                "code": exc.code,
                "message": exc.message,
                "request_id": turn.request_id,
                "conversation_id": turn.conversation_id,
                "message_id": turn.message_id,
            },
        )
        await append_event_stream(live, seq, "error", {"code": exc.code, "message": exc.message})
        logger.info(
            "RUN_FAILED tenant_id=%s message_id=%s request_id=%s code=%s",
            live.tenant_id,
            live.message_id,
            turn.request_id,
            exc.code,
        )
    except Exception:
        if not completed:
            try:
                await service.fail_before_run(turn, 50268)
            except Exception:
                logger.exception("fail_before_run after error message_id=%s", live.message_id)
        logger.exception(
            "RUN_FAILED tenant_id=%s message_id=%s request_id=%s",
            live.tenant_id,
            live.message_id,
            turn.request_id,
        )
        seq = live.publish(
            "error",
            {
                "code": 50268,
                "message": "模型生成失败",
                "request_id": turn.request_id,
                "conversation_id": turn.conversation_id,
                "message_id": turn.message_id,
            },
        )
        await append_event_stream(live, seq, "error", {"code": 50268})
    finally:
        await _quota("cancel")
        live.close()
        asyncio.create_task(_expire_run(live), name=f"expire-chat-run-{live.message_id}")
        await session.close()
        logger.info(
            "RUN_%s tenant_id=%s message_id=%s request_id=%s instance=%s",
            "COMPLETED" if completed else "INTERRUPTED",
            live.tenant_id,
            live.message_id,
            turn.request_id,
            WORKER_INSTANCE_ID,
        )


async def _expire_run(live: ChatLiveRun) -> None:
    delay = 0.05 if settings.is_test else min(120, max(30, settings.chat_lease_seconds))
    await asyncio.sleep(delay)
    current = hub.get(live.tenant_id, live.message_id)
    if current is live:
        hub.drop(live.tenant_id, live.message_id)
