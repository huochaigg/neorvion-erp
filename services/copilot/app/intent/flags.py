"""集中管理 Intent V15 Feature Flag，避免业务代码到处判断字符串。"""

from __future__ import annotations

from typing import Literal

from app.core.config import settings

IntentFeatureMode = Literal["DISABLED", "SHADOW", "ENABLED"]


def intent_mode() -> IntentFeatureMode:
    """读取统一 Feature Flag；未知值按 DISABLED 处理，避免错误开启新路由。"""
    value = (settings.intent_v15_mode or "DISABLED").strip().upper()
    if value in {"DISABLED", "SHADOW", "ENABLED"}:
        return value  # type: ignore[return-value]
    return "DISABLED"


def intent_active() -> bool:
    """SHADOW 或 ENABLED 时运行理解层并记录，DISABLED 时完全走旧路由。"""
    return intent_mode() in {"SHADOW", "ENABLED"}


def intent_applied() -> bool:
    """只有 ENABLED 才允许理解结果改写 Agent/Skill/Tool 路由。"""
    return intent_mode() == "ENABLED"


def intent_shadow() -> bool:
    return intent_mode() == "SHADOW"


def intent_llm_allowed() -> bool:
    """ENABLED 使用正式分类 LLM 开关；SHADOW 必须单独打开，避免隐性额外计费。"""
    if intent_mode() == "ENABLED":
        return bool(settings.intent_classifier_llm_enabled)
    if intent_mode() == "SHADOW":
        return bool(settings.intent_shadow_llm_enabled)
    return False
