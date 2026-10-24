"""Evidence Coverage：按必要事实覆盖，不改写 Chunk Recall / nDCG。

同一 fact：primary 或等价 alternative 命中任一即覆盖（OR）。
多个 required_facts：必须分别覆盖（AND）。
partial 不算完整覆盖。
无答案题不计算本指标。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.knowledge import ChunkStatus

EVIDENCE_COVERAGE_VERSION = "v1-fact-or-and"

_PRIMARY_PREFIXES = ("primary:", "fact:")
_ALT_PREFIXES = ("alt:", "alternative:")
_PARTIAL_PREFIX = "partial:"
_REQUIRED_PREFIX = "required_facts:"


@dataclass(frozen=True)
class FactEvidence:
    fact_id: str
    primary_chunk_ids: tuple[int, ...] = ()
    alternative_chunk_ids: tuple[int, ...] = ()
    partial_chunk_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class CaseEvidenceSpec:
    required_fact_ids: tuple[str, ...]
    facts: tuple[FactEvidence, ...] = ()

    def fact(self, fact_id: str) -> FactEvidence | None:
        for item in self.facts:
            if item.fact_id == fact_id:
                return item
        return None

    def all_chunk_ids(self) -> set[int]:
        ids: set[int] = set()
        for item in self.facts:
            ids.update(item.primary_chunk_ids)
            ids.update(item.alternative_chunk_ids)
            ids.update(item.partial_chunk_ids)
        return ids


@dataclass(frozen=True)
class LiveChunk:
    chunk_id: int
    tenant_id: int | None = None
    knowledge_base_id: int | None = None
    status: str | None = None
    enabled: bool = True


def _parse_int_ids(raw: str) -> list[int]:
    return [int(part) for part in raw.split(",") if part.strip().isdigit()]


def _tag_map(tags: list[str], prefixes: tuple[str, ...]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for tag in tags:
        matched = next((prefix for prefix in prefixes if tag.startswith(prefix)), None)
        if matched is None:
            continue
        body = tag[len(matched) :]
        if "=" not in body:
            continue
        fact_id, ids = body.split("=", 1)
        fact_id = fact_id.strip()
        if not fact_id:
            continue
        bucket = out.setdefault(fact_id, [])
        for chunk_id in _parse_int_ids(ids):
            if chunk_id not in bucket:
                bucket.append(chunk_id)
    return out


def parse_case_evidence(case: dict) -> CaseEvidenceSpec | None:
    """从冻结快照的 tags 恢复 required_facts / primary / alternative / partial。"""
    tags = [str(item) for item in (case.get("tags") or []) if isinstance(item, str)]
    required: list[str] = []
    for tag in tags:
        if tag.startswith(_REQUIRED_PREFIX):
            required = [part for part in tag.split(":", 1)[1].split("|") if part]
            break
    if not required:
        return None
    primary = _tag_map(tags, _PRIMARY_PREFIXES)
    alternative = _tag_map(tags, _ALT_PREFIXES)
    partial = _tag_map(tags, (_PARTIAL_PREFIX,))
    facts = []
    for fact_id in required:
        alt_ids = [cid for cid in alternative.get(fact_id, []) if cid not in set(primary.get(fact_id, []))]
        partial_ids = [
            cid
            for cid in partial.get(fact_id, [])
            if cid not in set(primary.get(fact_id, [])) and cid not in set(alt_ids)
        ]
        facts.append(
            FactEvidence(
                fact_id=fact_id,
                primary_chunk_ids=tuple(primary.get(fact_id, [])),
                alternative_chunk_ids=tuple(alt_ids),
                partial_chunk_ids=tuple(partial_ids),
            )
        )
    return CaseEvidenceSpec(required_fact_ids=tuple(required), facts=tuple(facts))


def reject_evidence_chunk(
    chunk_id: int,
    *,
    judgments: list[dict],
    live: LiveChunk | None,
    allowed_kb_ids: set[int],
    tenant_id: int | None,
) -> str | None:
    """返回拒绝原因；None 表示该 Chunk 可作为有效证据。"""
    for row in judgments:
        if int(row.get("chunk_id") or 0) == chunk_id and bool(row.get("stale")):
            return "stale"
    if live is None:
        return "missing"
    if tenant_id is not None and live.tenant_id is not None and live.tenant_id != tenant_id:
        return "wrong_tenant"
    if live.knowledge_base_id is None or live.knowledge_base_id not in allowed_kb_ids:
        return "wrong_kb"
    if live.status != ChunkStatus.ACTIVE.value:
        return "inactive"
    if not live.enabled:
        return "disabled"
    return None


def classify_evidence_chunks(
    spec: CaseEvidenceSpec,
    *,
    judgments: list[dict],
    live_chunks: dict[int, LiveChunk],
    allowed_kb_ids: set[int],
    tenant_id: int | None,
) -> tuple[set[int], dict[int, str]]:
    valid: set[int] = set()
    rejected: dict[int, str] = {}
    for chunk_id in spec.all_chunk_ids():
        reason = reject_evidence_chunk(
            chunk_id,
            judgments=judgments,
            live=live_chunks.get(chunk_id),
            allowed_kb_ids=allowed_kb_ids,
            tenant_id=tenant_id,
        )
        if reason:
            rejected[chunk_id] = reason
        else:
            valid.add(chunk_id)
    return valid, rejected


def evidence_coverage_metrics(
    ranked_ids: list[int],
    spec: CaseEvidenceSpec | None,
    *,
    k: int,
    valid_chunk_ids: set[int],
    rejected: dict[int, str] | None = None,
    is_unanswerable: bool = False,
) -> dict:
    """计算单题 Evidence Coverage。无答案或缺少必要事实时不给出覆盖率 1。"""
    payload: dict = {
        "evidence_coverage_version": EVIDENCE_COVERAGE_VERSION,
        "k": k,
    }
    if is_unanswerable:
        payload["evidence_coverage_skipped"] = "unanswerable"
        return payload
    if spec is None or not spec.required_fact_ids:
        payload["evidence_coverage_skipped"] = "no_required_facts"
        return payload

    rejected = rejected or {}
    top = set(ranked_ids[:k] if k > 0 else [])
    fact_rows = []
    unevaluable = []
    covered = 0
    for fact in spec.facts:
        valid_primary = [cid for cid in fact.primary_chunk_ids if cid in valid_chunk_ids]
        valid_alt = [cid for cid in fact.alternative_chunk_ids if cid in valid_chunk_ids]
        valid_partial = [cid for cid in fact.partial_chunk_ids if cid in valid_chunk_ids]
        fact_rejected = [
            {"chunk_id": cid, "reason": rejected[cid]}
            for cid in (*fact.primary_chunk_ids, *fact.alternative_chunk_ids, *fact.partial_chunk_ids)
            if cid in rejected
        ]
        if not valid_primary and not valid_alt:
            unevaluable.append(fact.fact_id)
            fact_rows.append(
                {
                    "fact_id": fact.fact_id,
                    "covered": False,
                    "evaluable": False,
                    "hit_role": None,
                    "hit_chunk_ids": [],
                    "primary_chunk_ids": list(fact.primary_chunk_ids),
                    "alternative_chunk_ids": list(fact.alternative_chunk_ids),
                    "partial_chunk_ids": list(fact.partial_chunk_ids),
                    "partial_hit_chunk_ids": [cid for cid in valid_partial if cid in top],
                    "rejected": fact_rejected,
                }
            )
            continue
        hit_primary = [cid for cid in valid_primary if cid in top]
        hit_alt = [cid for cid in valid_alt if cid in top]
        hit_partial = [cid for cid in valid_partial if cid in top]
        is_covered = bool(hit_primary or hit_alt)
        if is_covered:
            covered += 1
        if hit_primary:
            role = "primary"
            hits = hit_primary
        elif hit_alt:
            role = "alternative"
            hits = hit_alt
        else:
            role = None
            hits = []
        fact_rows.append(
            {
                "fact_id": fact.fact_id,
                "covered": is_covered,
                "evaluable": True,
                "hit_role": role,
                "hit_chunk_ids": hits,
                "primary_chunk_ids": list(fact.primary_chunk_ids),
                "alternative_chunk_ids": list(fact.alternative_chunk_ids),
                "partial_chunk_ids": list(fact.partial_chunk_ids),
                "partial_hit_chunk_ids": hit_partial,
                "rejected": fact_rejected,
            }
        )

    if unevaluable:
        payload["evidence_coverage_skipped"] = "unevaluable_evidence"
        payload["unevaluable_facts"] = unevaluable
        payload["required_facts"] = list(spec.required_fact_ids)
        payload["facts"] = fact_rows
        payload["uncovered_facts"] = [row["fact_id"] for row in fact_rows if not row["covered"]]
        return payload

    total = len(spec.required_fact_ids)
    coverage = 0.0 if total == 0 or k <= 0 else covered / total
    complete = bool(total > 0 and k > 0 and covered == total)
    payload.update(
        {
            "evidence_coverage_at_k": coverage,
            "complete_evidence_at_k": complete,
            "required_fact_count": total,
            "covered_fact_count": covered,
            "required_facts": list(spec.required_fact_ids),
            "facts": fact_rows,
            "uncovered_facts": [row["fact_id"] for row in fact_rows if not row["covered"]],
        }
    )
    return payload


def aggregate_evidence_coverage(rows: list[dict]) -> dict:
    """只对写出 coverage 数值的题目做宏平均。历史 Run 没有这些字段时返回空。"""
    scored = [row for row in rows if isinstance(row.get("evidence_coverage_at_k"), (int, float))]
    skipped = [row for row in rows if row.get("evidence_coverage_skipped")]
    if not scored and not skipped:
        return {}
    result: dict = {
        "evidence_coverage_version": EVIDENCE_COVERAGE_VERSION,
        "evidence_coverage_count": len(scored),
        "evidence_coverage_skipped_count": len(skipped),
    }
    if scored:
        result["evidence_coverage"] = sum(float(row["evidence_coverage_at_k"]) for row in scored) / len(scored)
        result["complete_evidence_rate"] = sum(
            1.0 if row.get("complete_evidence_at_k") else 0.0 for row in scored
        ) / len(scored)
    return result
