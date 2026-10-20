"""比较两份数据集冻结快照。只看快照里的题目和标注，不读当前工作稿。"""

from __future__ import annotations

_FIELDS = (
    "question",
    "expected_answer",
    "question_type",
    "difficulty",
    "is_unanswerable",
    "annotation_status",
)


def diff_snapshots(left_cases: list[dict], right_cases: list[dict]) -> dict:
    """右版本相对左版本：新增、删除、修改。题目以 case id 对齐。

    标注比较与顺序无关。未变化的题目只计数，不放进 changes。
    """
    left = _by_id(left_cases)
    right = _by_id(right_cases)
    changes = []
    unchanged = 0
    for case_id in sorted(set(left) | set(right)):
        before = left.get(case_id)
        after = right.get(case_id)
        if before is None and after is not None:
            changes.append({"change": "ADDED", "case_id": case_id, "fields": [], "before": None, "after": after})
            continue
        if before is not None and after is None:
            changes.append({"change": "REMOVED", "case_id": case_id, "fields": [], "before": before, "after": None})
            continue
        fields = _changed_fields(before or {}, after or {})
        if fields:
            changes.append(
                {"change": "MODIFIED", "case_id": case_id, "fields": fields, "before": before, "after": after}
            )
        else:
            unchanged += 1
    return {
        "added_count": sum(1 for item in changes if item["change"] == "ADDED"),
        "removed_count": sum(1 for item in changes if item["change"] == "REMOVED"),
        "modified_count": sum(1 for item in changes if item["change"] == "MODIFIED"),
        "unchanged_count": unchanged,
        "changes": changes,
    }


def _by_id(cases: list[dict]) -> dict[int, dict]:
    found = {}
    for item in cases:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        found[int(item["id"])] = item
    return found


def _changed_fields(before: dict, after: dict) -> list[str]:
    changed = [name for name in _FIELDS if before.get(name) != after.get(name)]
    if _tags(before) != _tags(after):
        changed.append("tags")
    if _judgments(before) != _judgments(after):
        changed.append("judgments")
    return changed


def _tags(case: dict) -> tuple[str, ...]:
    raw = case.get("tags") or []
    if not isinstance(raw, list):
        return ()
    return tuple(sorted(str(item) for item in raw))


def _judgments(case: dict) -> tuple:
    rows = []
    for item in case.get("judgments") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            (
                item.get("chunk_id"),
                item.get("relevance"),
                bool(item.get("stale")),
                item.get("source_key"),
                item.get("content_hash"),
            )
        )
    return tuple(sorted(rows, key=lambda row: (row[0] is None, row[0] or 0, row[1] or 0)))
