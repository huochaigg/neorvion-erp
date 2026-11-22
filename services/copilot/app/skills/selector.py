from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field, replace
from typing import Any

from app.ai.types import ChatAdapter, ModelUsage
from app.core.config import settings
from app.core.exceptions import AppError
from app.skills.catalog import SkillCatalogEntry
from app.skills.classification import TaskClassification, TaskClassifier


@dataclass(frozen=True, slots=True)
class SkillCandidate:
    skill_key: str
    score: float
    signals: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SkillSelection:
    selected_skills: tuple[SkillCatalogEntry, ...]
    method: str
    reason: str
    confidence: float
    classification: TaskClassification
    candidates: tuple[SkillCandidate, ...] = ()
    selector_latency_ms: float = 0
    llm_involved: bool = False
    llm_usage: ModelUsage | None = None
    recall_method: str = "NONE"
    config_version: str = "v14.3"
    catalog_trace: dict[str, Any] = field(default_factory=dict)

    @property
    def selected(self) -> SkillCatalogEntry | None:
        """兼容 V14.1++ 单 Skill 调用方。"""
        return self.selected_skills[0] if len(self.selected_skills) == 1 else None


class SkillSelector:
    """通用级联选择器：显式指定→高置信规则→轻量语义召回→可选 LLM 裁决。"""

    _explicit = re.compile(r"(?:@|使用\s*)([a-z][a-z0-9-]{2,79})(?:\s*技能)?", re.I)

    def __init__(
        self,
        classifier: TaskClassifier | None = None,
        *,
        top_k: int | None = None,
        recall_threshold: float | None = None,
        rule_threshold: float | None = None,
        lexical_threshold: float | None = None,
        ambiguity_margin: float | None = None,
    ) -> None:
        self.classifier = classifier or TaskClassifier()
        self.top_k = top_k if top_k is not None else settings.skill_selector_top_k
        self.recall_threshold = recall_threshold if recall_threshold is not None else settings.skill_selector_recall_threshold
        self.rule_threshold = rule_threshold if rule_threshold is not None else settings.skill_selector_rule_threshold
        self.lexical_threshold = lexical_threshold if lexical_threshold is not None else settings.skill_selector_semantic_threshold
        self.ambiguity_margin = ambiguity_margin if ambiguity_margin is not None else settings.skill_selector_ambiguity_margin

    async def select(
        self,
        task: str,
        catalog: list[SkillCatalogEntry],
        *,
        explicit_skill_key: str | None = None,
        adapter: ChatAdapter | None = None,
        catalog_trace: dict[str, Any] | None = None,
    ) -> SkillSelection:
        started = time.perf_counter()

        def done(value: SkillSelection) -> SkillSelection:
            return replace(
                value,
                selector_latency_ms=round((time.perf_counter() - started) * 1000, 3),
                catalog_trace=catalog_trace or {},
            )

        classification = self.classifier.classify(task)
        available = {item.skill_key: item for item in catalog}
        if settings.skill_selector_mode.upper() == "LEGACY" and explicit_skill_key is None:
            return done(self._legacy(task, available, classification))
        text_explicit = self._explicit_key(task, available)
        if explicit_skill_key and text_explicit and explicit_skill_key != text_explicit:
            raise AppError(
                "UI 指定的 Skill 与消息中的 @Skill 不一致",
                code=40989,
                status_code=409,
            )
        explicit = explicit_skill_key or text_explicit
        if explicit:
            item = available.get(explicit)
            if item is None:
                raise AppError(
                    "指定的 Skill 不存在、未启用或当前用户无权运行",
                    code=40488,
                    status_code=404,
                )
            return done(SkillSelection((item,), "EXPLICIT", "用户显式指定已授权 Skill", 1, classification))
        if classification.negative_action:
            return done(SkillSelection(
                (),
                "NO_SKILL",
                "检测到否定式操作表述；不自动触发业务 Skill，交由普通对话解释",
                1,
                classification,
            ))
        if classification.intent == "GENERAL_CHAT" or classification.risk != "READ_ONLY":
            return done(SkillSelection((), "NO_SKILL", "普通对话或写操作请求不自动触发只读 Skill", 1, classification))
        candidates = self._recall(task, catalog)
        if not candidates:
            return done(SkillSelection((), "NO_SKILL", "没有达到召回阈值的 Skill", 0, classification, recall_method="LEXICAL"))
        top = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        margin = top.score - (second.score if second else 0)
        if top.score >= self.rule_threshold and margin >= 0.12:
            return done(SkillSelection((available[top.skill_key],), "RULE", "名称、描述和任务领域形成高置信匹配", top.score, classification, candidates, recall_method="LEXICAL"))
        multi = self._multi_domain_selection(classification, candidates, available)
        if multi and settings.skill_multi_enabled:
            keys = {item.skill_key for item in multi}
            return done(SkillSelection(multi, "LEXICAL", "跨领域任务命中多个互补 Skill", min(item.score for item in candidates if item.skill_key in keys), classification, candidates, recall_method="LEXICAL"))
        if adapter is not None and settings.skill_selector_llm_enabled and len(candidates) > 1:
            decided = await self._llm_select(task, classification, candidates, available, adapter)
            if decided is not None:
                return done(replace(decided, llm_involved=True, recall_method="LEXICAL"))
        if top.score >= self.lexical_threshold and (second is None or margin >= self.ambiguity_margin):
            return done(SkillSelection((available[top.skill_key],), "LEXICAL", "轻量词项召回达到阈值", top.score, classification, candidates, recall_method="LEXICAL"))
        return done(SkillSelection((), "AMBIGUOUS", "多个候选无法可靠区分，需要澄清", top.score, classification, candidates, recall_method="LEXICAL"))

    def _legacy(
        self,
        task: str,
        available: dict[str, SkillCatalogEntry],
        classification: TaskClassification,
    ) -> SkillSelection:
        """Feature Flag 关闭时保持 V14.1++ 三个内置 Skill 的保守双信号行为。"""
        rules = {
            "inventory-analysis": (r"\bsku[-_a-z0-9]*\b", r"库存|覆盖天数|缺货|inventory|stock|coverage"),
            "sales-order-review": (r"销售订单|订单审查|sales\s+order|\bso[-_0-9]+\b", r"审查|检查|风险|review|audit"),
            "knowledge-research": (r"制度|政策|规定|知识库|流程|policy|knowledge|procedure", r"查询|查找|查一下|查一查|研究|了解|依据|来源|search|research|find"),
        }
        matched = [
            available[key]
            for key, patterns in rules.items()
            if key in available and all(re.search(pattern, task, re.I) for pattern in patterns)
        ]
        if len(matched) == 1:
            return SkillSelection(tuple(matched), "RULE", "V14.1++ 双信号规则匹配", 1, classification)
        return SkillSelection((), "AMBIGUOUS" if matched else "NO_SKILL", "V14.1++ 安全回退", 0, classification)

    def _recall(self, task: str, catalog: list[SkillCatalogEntry]) -> tuple[SkillCandidate, ...]:
        query = self._terms(task)
        output: list[SkillCandidate] = []
        for item in catalog:
            document = self._terms(" ".join((item.skill_key, item.name, item.description, self._metadata_text(item.metadata))))
            overlap = query & document
            if not overlap:
                continue
            coverage = len(overlap) / max(1, len(query))
            specificity = len(overlap) / max(1, min(len(document), 18))
            name_hit = 0.25 if self._terms(item.name) & query else 0
            score = min(1.0, coverage * 0.55 + specificity * 0.20 + name_hit)
            if score >= self.recall_threshold:
                output.append(SkillCandidate(item.skill_key, round(score, 4), tuple(sorted(overlap))[:8]))
        output.sort(key=lambda item: (-item.score, item.skill_key))
        return tuple(output[: self.top_k])

    @staticmethod
    def _terms(value: str) -> set[str]:
        lowered = value.lower()
        ascii_terms = set(re.findall(r"[a-z0-9][a-z0-9_-]+", lowered))
        chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
        grams = {chinese[index : index + 2] for index in range(max(0, len(chinese) - 1))}
        return ascii_terms | grams

    @staticmethod
    def _metadata_text(metadata: dict[str, Any]) -> str:
        values: list[str] = []
        for key in ("description", "category", "aliases", "trigger_phrases", "use_cases"):
            value = metadata.get(key)
            if isinstance(value, str):
                values.append(value)
            elif isinstance(value, list):
                values.extend(str(item) for item in value[:20])
        nested = metadata.get("metadata")
        if isinstance(nested, dict):
            values.extend(str(item) for item in nested.values())
        return " ".join(values)

    @classmethod
    def _explicit_key(cls, task: str, available: dict[str, SkillCatalogEntry]) -> str | None:
        match = cls._explicit.search(task)
        if match:
            return match.group(1).lower()
        for key, item in available.items():
            if f"使用{item.name}" in task or f"用{item.name}" in task:
                return key
        return None

    def _multi_domain_selection(self, classification: TaskClassification, candidates: tuple[SkillCandidate, ...], available: dict[str, SkillCatalogEntry]) -> tuple[SkillCatalogEntry, ...]:
        if classification.complexity != "MULTI_DOMAIN":
            return ()
        selected = [available[item.skill_key] for item in candidates if item.score >= self.lexical_threshold]
        return tuple(selected[: settings.skill_plan_max_steps]) if len(selected) >= 2 else ()

    async def _llm_select(self, task: str, classification: TaskClassification, candidates: tuple[SkillCandidate, ...], available: dict[str, SkillCatalogEntry], adapter: ChatAdapter) -> SkillSelection | None:
        """LLM 只在歧义候选上裁决；输出必须经严格 JSON、候选集和置信度校验。"""
        payload = [{"skill_key": item.skill_key, "name": available[item.skill_key].name, "description": available[item.skill_key].description} for item in candidates]
        prompt = (
            "只输出 JSON：{\"selected_skill_keys\":[],\"confidence\":0.0,\"reason\":\"\"}。"
            "只能从候选选择；不需要技能或不确定时返回空数组。\n"
            f"分类：{json.dumps(classification.as_dict(), ensure_ascii=False)}\n"
            f"候选：{json.dumps(payload, ensure_ascii=False)}\n任务：{task}"
        )
        chunks: list[str] = []
        usage: ModelUsage | None = None
        try:
            async with asyncio.timeout(settings.skill_selector_llm_timeout_seconds):
                async for delta in adapter.stream([{"role": "user", "content": prompt}]):
                    if delta.text:
                        chunks.append(delta.text)
                    if delta.usage is not None:
                        usage = delta.usage
            raw = json.loads("".join(chunks))
            keys = raw.get("selected_skill_keys")
            confidence = float(raw.get("confidence"))
            if not isinstance(keys, list) or not 0 <= confidence <= 1:
                return None
            clean = tuple(dict.fromkeys(str(key) for key in keys))
            if len(clean) > settings.skill_plan_max_steps or any(key not in available for key in clean):
                return None
            if confidence < settings.skill_selector_llm_confidence_threshold or not clean:
                return SkillSelection((), "AMBIGUOUS", "LLM 裁决置信度不足", confidence, classification, candidates, llm_usage=usage)
            return SkillSelection(tuple(available[key] for key in clean), "LLM", str(raw.get("reason") or "结构化模型裁决")[:200], confidence, classification, candidates, llm_usage=usage)
        except (TimeoutError, ValueError, TypeError, json.JSONDecodeError):
            return None
