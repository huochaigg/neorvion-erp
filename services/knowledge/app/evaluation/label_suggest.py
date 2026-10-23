"""把模型给出的切片建议收成可审核草稿。

相关性沿用 metrics.py：0–3 级，relevance >= 1 才算相关。
这里不写数据库，也不把题目标成 READY。未知切片会被丢掉，不能升成高置信度。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.evaluation.judge import collect_chat

LABEL_PROMPT_VERSION = "v8-label-1"
_VERDICTS = {"ANSWERABLE", "UNANSWERABLE", "PARTIAL", "CONFLICT", "INSUFFICIENT"}
_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


@dataclass
class LabelCandidate:
    chunk_id: int
    document_id: int
    filename: str
    content: str
    chunk_version: int
    content_hash: str
    methods: list[str] = field(default_factory=list)


@dataclass
class LabelDraft:
    verdict: str
    confidence: str
    rationale: str
    risk: str
    items: list[dict]
    model_name: str
    prompt_version: str = LABEL_PROMPT_VERSION


def estimate_label_calls(case_count: int) -> dict:
    """只估算调用次数。文档向量复用已有结果，不计入。"""
    pending = max(case_count, 0)
    return {
        "chat_calls": pending,
        "embedding_calls": pending,
        "document_embedding_calls": 0,
        "retry_limit": settings.eval_model_retries,
        "worst_chat_calls": pending * (1 + settings.eval_model_retries),
        "chat_model": settings.chat_model,
        "embedding_model": settings.embedding_model,
    }


def finalize_label(
    *,
    judge: dict,
    candidates: list[LabelCandidate],
    is_unanswerable: bool,
    question_type: str,
    model_name: str,
) -> LabelDraft:
    """丢掉模型编造的切片，并在证据不足或与题目定义冲突时降低置信度。"""
    allowed = {item.chunk_id: item for item in candidates}
    notes: list[str] = []
    raw_items = judge.get("items")
    kept: list[dict] = []
    seen: set[int] = set()
    dropped = 0
    remapped = 0
    for raw in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw, dict):
            dropped += 1
            continue
        try:
            chunk_id = int(raw.get("chunk_id") or 0)
            relevance = int(raw.get("relevance") or 0)
        except (TypeError, ValueError):
            dropped += 1
            continue
        if relevance < 0 or relevance > 3:
            dropped += 1
            continue
        excerpt = str(raw.get("excerpt") or "")[:500]
        candidate = allowed.get(chunk_id)
        if candidate is None:
            candidate = _match_candidate_by_excerpt(excerpt, candidates)
            if candidate is None:
                dropped += 1
                continue
            remapped += 1
            notes.append(f"模型切片 #{chunk_id} 不在候选中，已按摘录对齐到 #{candidate.chunk_id}")
        if candidate.chunk_id in seen:
            continue
        seen.add(candidate.chunk_id)
        if excerpt and excerpt not in candidate.content:
            excerpt = candidate.content[:240]
            notes.append(f"Chunk {candidate.chunk_id} 的摘录不在原文中，已改用原文开头")
        elif not excerpt:
            excerpt = candidate.content[:240]
        kept.append(
            {
                "chunk_id": candidate.chunk_id,
                "document_id": candidate.document_id,
                "filename": candidate.filename,
                "relevance": relevance,
                "reason": str(raw.get("reason") or "")[:500],
                "excerpt": excerpt,
                "chunk_version": candidate.chunk_version,
                "content_hash": candidate.content_hash,
                "methods": list(candidate.methods),
            }
        )
    if remapped:
        notes.append(f"已按摘录对齐 {remapped} 条切片，无需人工填写 ID")
    if dropped:
        notes.append(f"丢弃了 {dropped} 条无法对应到本知识库切片的建议")

    verdict = str(judge.get("verdict") or "").upper()
    if verdict not in _VERDICTS:
        verdict = "INSUFFICIENT"
        notes.append("模型没有给出合法结论")
    confidence = str(judge.get("confidence") or "LOW").upper()
    if confidence not in _CONFIDENCE:
        confidence = "LOW"

    if verdict == "UNANSWERABLE":
        removed = [item for item in kept if item["relevance"] >= 1]
        kept = [item for item in kept if item["relevance"] < 1]
        if removed:
            notes.append("无答案结论不保留正相关切片")
        if not is_unanswerable:
            notes.append("题目当前不是无答案题，不能按一次模型结论改成无答案")
            confidence = _lower(confidence, "LOW")
    elif is_unanswerable:
        notes.append("题目定义为无答案，但模型认为可以回答，需要人工判断")
        confidence = _lower(confidence, "LOW")

    positive = [item for item in kept if item["relevance"] >= 1]
    strong = [item for item in kept if item["relevance"] >= 2]
    if verdict == "ANSWERABLE" and not positive:
        verdict = "INSUFFICIENT"
        notes.append("没有正相关切片，不能当成可回答")
        confidence = _lower(confidence, "LOW")
    if question_type in {"MULTI_DOC", "MULTI_CONDITION"} and len(strong) < 2 and verdict != "UNANSWERABLE":
        notes.append("多文档或多条件题还没有两处以上较强证据")
        confidence = _lower(confidence, "MEDIUM")
    if dropped:
        confidence = _lower(confidence, "MEDIUM")

    rationale = str(judge.get("rationale") or "")[:1000]
    risk = str(judge.get("risk") or "")[:1000]
    extra = "；".join(notes)
    if extra:
        risk = f"{risk}；{extra}" if risk else extra
    return LabelDraft(
        verdict=verdict,
        confidence=confidence,
        rationale=rationale,
        risk=risk,
        items=kept,
        model_name=model_name,
    )


def _match_candidate_by_excerpt(excerpt: str, candidates: list[LabelCandidate]) -> LabelCandidate | None:
    quote = excerpt.strip()
    if len(quote) < 12:
        return None
    hits = [item for item in candidates if quote in item.content]
    if len(hits) == 1:
        return hits[0]
    return None


def _lower(current: str, ceiling: str) -> str:
    if _RANK[current] <= _RANK[ceiling]:
        return current
    return ceiling


async def judge_relevance(
    *,
    question: str,
    expected_answer: str | None,
    question_type: str,
    is_unanswerable: bool,
    candidates: list[LabelCandidate],
) -> dict:
    """请模型只在给定切片里打分。调用失败时抛出异常，由上层记失败草稿。"""
    blocks = []
    for item in candidates:
        blocks.append(
            "\n".join(
                [
                    f'<chunk id="{item.chunk_id}" file="{item.filename}" methods="{",".join(item.methods)}">',
                    item.content[:1500],
                    "</chunk>",
                ]
            )
        )
    messages = [
        {
            "role": "system",
            "content": (
                "你是知识库标注助手，只输出一个 JSON 对象。"
                "只能使用给定 chunk id，禁止编造。"
                "relevance 取 0、1、2、3：0 无关，1 只有背景，2 支持部分答案，3 直接支持关键结论。"
                "relevance >= 1 才会被检索指标当成相关。"
                "verdict 取 ANSWERABLE、UNANSWERABLE、PARTIAL、CONFLICT、INSUFFICIENT。"
                "confidence 取 HIGH、MEDIUM、LOW，它只是审核优先级，不是正确率。"
                "题目当前标记无答案为 false 时，禁止输出 UNANSWERABLE。"
                "题型 HALLUCINATION 且不是无答案时，应输出 ANSWERABLE 或 PARTIAL，并引用纠正错误前提的切片。"
                "无答案必须 items 里不放 relevance>=1 的切片。"
                "证据不够、文档冲突或只能回答一部分时降低 confidence，并在 risk 里说明。"
                f"prompt_version={LABEL_PROMPT_VERSION}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"问题：{question}\n"
                f"标准答案：{expected_answer or '（无）'}\n"
                f"题型：{question_type}\n"
                f"题目当前标记无答案：{str(is_unanswerable).lower()}\n\n"
                f"候选切片：\n{chr(10).join(blocks) or '（全文扫描没有切片）'}"
            ),
        },
    ]
    text, _usage = await collect_chat(messages)
    return _extract_json(text)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("模型没有返回 JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("模型返回的不是对象")
    return data
