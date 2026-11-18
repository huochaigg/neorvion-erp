from __future__ import annotations

import re
from dataclasses import dataclass

from app.skills.catalog import SkillCatalogEntry


@dataclass(frozen=True, slots=True)
class SkillSelection:
    selected: SkillCatalogEntry | None
    method: str
    reason: str
    candidates: tuple[str, ...] = ()


class SkillSelector:
    """三个内置技能采用保守规则选择；无匹配或并列歧义均返回 NO_SKILL。"""

    _RULES = {
        "inventory-analysis": (
            re.compile(r"\bsku[-_a-z0-9]*\b", re.I),
            re.compile(r"库存|覆盖天数|缺货|inventory|stock|coverage", re.I),
        ),
        "sales-order-review": (
            re.compile(r"销售订单|订单审查|sales\s+order|\bso[-_0-9]+\b", re.I),
            re.compile(r"审查|检查|风险|review|audit", re.I),
        ),
        "knowledge-research": (
            re.compile(r"制度|政策|规定|知识库|流程|policy|knowledge|procedure", re.I),
            re.compile(r"查询|查找|查一下|查一查|研究|了解|依据|来源|search|research|find", re.I),
        ),
    }

    def select(self, task: str, catalog: list[SkillCatalogEntry]) -> SkillSelection:
        text = task.strip()
        scores: list[tuple[int, SkillCatalogEntry]] = []
        for item in catalog:
            patterns = self._RULES.get(item.skill_key, ())
            score = sum(bool(pattern.search(text)) for pattern in patterns)
            if score:
                scores.append((score, item))
        if not scores:
            return SkillSelection(None, "NO_SKILL", "没有明确匹配的已授权 Skill")
        best = max(score for score, _ in scores)
        candidates = [item for score, item in scores if score == best]
        if best < 2 or len(candidates) != 1:
            return SkillSelection(
                None,
                "AMBIGUOUS",
                "候选意图不够明确，保留原有 Chat 路径",
                tuple(item.skill_key for item in candidates),
            )
        selected = candidates[0]
        return SkillSelection(
            selected,
            "DETERMINISTIC_RULE",
            f"任务与 {selected.skill_key} 的两个独立意图信号匹配",
            (selected.skill_key,),
        )
