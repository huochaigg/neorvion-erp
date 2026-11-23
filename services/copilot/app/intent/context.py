"""轻量上下文解析：补齐指代，不建设长期记忆，不跨租户引用。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.intent.schemas import ContextEntity, ContextSource, ConversationContext

_SKU = re.compile(r"\bsku[-_]?[a-z0-9]+\b", re.I)
_ORDER = re.compile(r"\b(?:so|order)[-_]?[a-z0-9]+\b", re.I)
_ANAPHORA = re.compile(r"(这个|那个|它|刚才|上面|上次|他们|那个商品|按刚才)")
_DO_IT = re.compile(r"(按刚才说的办|就这么办|直接执行|那就按)")
_SHORT = re.compile(r"^(分析一下|再看看|继续|好的|嗯)[！!。.?？\s]*$")


class ContextResolver:
    """
    输入：当前消息、最近对话、已持久化实体、待补全任务和待确认动作。
    输出：ConversationContext。
    流程：隔离租户 → 抽取可信实体 → 识别指代 → 绑定 pending。
    边界：助手文本与工具结果不可信；历史不能绕过当前权限。
    """

    def resolve(
        self,
        *,
        tenant_id: int,
        user_id: int,
        conversation_id: int | None,
        current_text: str,
        recent_messages: list[dict[str, str]] | None = None,
        stored_entities: list[dict[str, Any]] | None = None,
        pending: dict[str, Any] | None = None,
        pending_skill_key: str | None = None,
        has_open_proposal: bool = False,
    ) -> ConversationContext:
        history = list(recent_messages or [])[-settings.intent_context_max_messages :]
        user_texts = tuple(
            str(item.get("content") or "")[: settings.chat_max_message_chars]
            for item in history
            if item.get("role") == "user"
        )
        assistant_texts = tuple(
            str(item.get("content") or "")[:400]
            for item in history
            if item.get("role") == "assistant"
        )
        entities = self._merge_entities(current_text, user_texts, assistant_texts, stored_entities)
        anaphora = bool(_ANAPHORA.search(current_text) or _SHORT.fullmatch(current_text.strip()))
        pending = pending or {}
        refs = tuple(
            f"{item.source}:{item.name}"
            for item in entities
        )
        if pending.get("intent_key"):
            refs = (*refs, "pending_intent")
        if pending_skill_key:
            refs = (*refs, "pending_skill")
        if has_open_proposal:
            refs = (*refs, "pending_proposal")
        if _DO_IT.search(current_text):
            refs = (*refs, "confirmation_phrase")
        return ConversationContext(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            current_text=current_text.strip()[: settings.chat_max_message_chars],
            recent_user_texts=user_texts[-4:],
            recent_assistant_texts=assistant_texts[-2:],
            entities=entities,
            pending_intent_key=str(pending["intent_key"]) if pending.get("intent_key") else None,
            pending_slots=dict(pending.get("slots") or {})
            if isinstance(pending.get("slots"), dict)
            else {},
            pending_missing=tuple(str(item) for item in (pending.get("missing") or ())),
            pending_skill_key=pending_skill_key,
            has_open_proposal=has_open_proposal,
            anaphora=anaphora,
            context_dependent=anaphora or bool(_SHORT.fullmatch(current_text.strip())),
            refs=tuple(dict.fromkeys(refs)),
        )

    def _merge_entities(
        self,
        current: str,
        user_texts: tuple[str, ...],
        assistant_texts: tuple[str, ...],
        stored: list[dict[str, Any]] | None,
    ) -> tuple[ContextEntity, ...]:
        found: dict[tuple[str, str], ContextEntity] = {}

        def add(name: str, value: str, source: ContextSource, trusted: bool) -> None:
            key = (name, value.upper())
            previous = found.get(key)
            if previous and previous.trusted and not trusted:
                return
            found[key] = ContextEntity(
                name=name, value=value.upper(), source=source, trusted=trusted
            )

        for sku in _SKU.findall(current):
            add("sku_code", sku, "current_message", True)
        for order in _ORDER.findall(current):
            add("order_id", order, "current_message", True)
        for text in user_texts:
            for sku in _SKU.findall(text):
                add("sku_code", sku, "recent_user_message", True)
            for order in _ORDER.findall(text):
                add("order_id", order, "recent_user_message", True)
        for text in assistant_texts:
            for sku in _SKU.findall(text):
                add("sku_code", sku, "recent_assistant_message", False)
        for raw in stored or []:
            name = str(raw.get("name") or "")
            value = str(raw.get("value") or "")
            if not name or not value:
                continue
            add(
                name,
                value,
                str(raw.get("source") or "inferred"),  # type: ignore[arg-type]
                bool(raw.get("trusted")),
            )
        return tuple(found.values())[:20]


def context_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    current = datetime.now(UTC)
    if expires_at.tzinfo is None:
        return True
    return expires_at <= current
