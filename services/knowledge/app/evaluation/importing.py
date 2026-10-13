"""评测问题导入。支持 CSV / JSONL / 简易 xlsx，不把知识库正文当指令执行。"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass

from app.core.exceptions import AppError
from app.models.evaluation import QuestionType

_NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
_COLUMN_ALIASES = {
    "question": "question",
    "问题": "question",
    "expected_answer": "expected_answer",
    "answer": "expected_answer",
    "标准答案": "expected_answer",
    "question_type": "question_type",
    "类型": "question_type",
    "difficulty": "difficulty",
    "难度": "difficulty",
    "tags": "tags",
    "标签": "tags",
    "is_unanswerable": "is_unanswerable",
    "无答案": "is_unanswerable",
}


@dataclass
class ImportRow:
    row_number: int
    question: str
    expected_answer: str | None
    question_type: str
    difficulty: int
    tags: list[str]
    is_unanswerable: bool
    error: str | None = None


def parse_table(filename: str, payload: bytes) -> tuple[list[ImportRow], list[dict]]:
    """解析上传文件。errors 为无法形成题目的行。"""
    name = filename.lower()
    if name.endswith(".csv"):
        rows = _from_dicts(_csv_dicts(payload))
    elif name.endswith(".jsonl") or name.endswith(".json"):
        rows = _from_dicts(_jsonl_dicts(payload))
    elif name.endswith(".xlsx"):
        rows = _from_dicts(_xlsx_dicts(payload))
    else:
        raise AppError("仅支持 CSV、JSONL、XLSX", code=40080, status_code=400)
    ok = [item for item in rows if item.error is None]
    errors = [{"row": item.row_number, "message": item.error} for item in rows if item.error]
    return ok, errors


def _csv_dicts(payload: bytes) -> list[tuple[int, dict[str, str]]]:
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise AppError("CSV 缺少表头", code=40081, status_code=400)
    return [
        (index, {_normalize_header(str(k)): str(v or "") for k, v in row.items() if k is not None})
        for index, row in enumerate(reader, start=2)
    ]


def _jsonl_dicts(payload: bytes) -> list[tuple[int, dict[str, str]]]:
    items: list[tuple[int, dict[str, str]]] = []
    for index, line in enumerate(payload.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            items.append((index, {"__error": "JSON 无法解析"}))
            continue
        if not isinstance(raw, dict):
            items.append((index, {"__error": "每行必须是对象"}))
            continue
        items.append((index, {_normalize_header(str(k)): "" if v is None else str(v) for k, v in raw.items()}))
    return items


def _xlsx_dicts(payload: bytes) -> list[tuple[int, dict[str, str]]]:
    """读取第一个工作表。只支持共享字符串与内联文本的简单表格。"""
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            shared = _shared_strings(archive)
            sheet_name = "xl/worksheets/sheet1.xml"
            if sheet_name not in archive.namelist():
                raise AppError("Excel 中没有第一个工作表", code=40082, status_code=400)
            root = ET.fromstring(archive.read(sheet_name))
    except zipfile.BadZipFile as exc:
        raise AppError("Excel 文件无法解析", code=40082, status_code=400) from exc
    grid: dict[tuple[int, int], str] = {}
    max_col = 0
    max_row = 0
    for cell in root.findall(".//m:c", _NS):
        ref = cell.get("r") or "A1"
        col, row = _split_ref(ref)
        value_node = cell.find("m:v", _NS)
        if value_node is None or value_node.text is None:
            continue
        raw = value_node.text
        if cell.get("t") == "s":
            raw = shared[int(raw)] if raw.isdigit() and int(raw) < len(shared) else raw
        grid[(row, col)] = raw
        max_col = max(max_col, col)
        max_row = max(max_row, row)
    if max_row < 1:
        raise AppError("Excel 为空", code=40081, status_code=400)
    headers = [_normalize_header(grid.get((1, col), "")) for col in range(1, max_col + 1)]
    items: list[tuple[int, dict[str, str]]] = []
    for row in range(2, max_row + 1):
        mapping = {headers[col - 1]: grid.get((row, col), "") for col in range(1, max_col + 1) if headers[col - 1]}
        items.append((row, mapping))
    return items


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    name = "xl/sharedStrings.xml"
    if name not in archive.namelist():
        return []
    root = ET.fromstring(archive.read(name))
    values = []
    for item in root.findall("m:si", _NS):
        texts = [node.text or "" for node in item.findall(".//m:t", _NS)]
        values.append("".join(texts))
    return values


def _split_ref(ref: str) -> tuple[int, int]:
    letters = "".join(ch for ch in ref if ch.isalpha())
    digits = "".join(ch for ch in ref if ch.isdigit())
    col = 0
    for ch in letters.upper():
        col = col * 26 + (ord(ch) - 64)
    return int(digits or 1), col


def _normalize_header(value: str) -> str:
    key = value.strip()
    return _COLUMN_ALIASES.get(key, _COLUMN_ALIASES.get(key.lower(), key.lower()))


def _from_dicts(rows: list[tuple[int, dict[str, str]]]) -> list[ImportRow]:
    parsed: list[ImportRow] = []
    types = {item.value for item in QuestionType}
    for row_number, raw in rows:
        if raw.get("__error"):
            parsed.append(
                ImportRow(row_number, "", None, QuestionType.FACTUAL.value, 2, [], False, raw["__error"])
            )
            continue
        question = (raw.get("question") or "").strip()
        if not question:
            parsed.append(ImportRow(row_number, "", None, QuestionType.FACTUAL.value, 2, [], False, "缺少问题"))
            continue
        qtype = (raw.get("question_type") or QuestionType.FACTUAL.value).strip().upper()
        if qtype not in types:
            qtype = QuestionType.FACTUAL.value
        try:
            difficulty = int(float(raw.get("difficulty") or 2))
        except ValueError:
            difficulty = 2
        difficulty = min(max(difficulty, 1), 5)
        tags_raw = raw.get("tags") or ""
        tags = [item.strip() for item in tags_raw.replace("，", ",").split(",") if item.strip()]
        flag = (raw.get("is_unanswerable") or "").strip().lower()
        is_unanswerable = flag in {"1", "true", "yes", "y", "是"} or qtype == QuestionType.UNANSWERABLE.value
        expected = (raw.get("expected_answer") or "").strip() or None
        parsed.append(
            ImportRow(row_number, question, expected, qtype, difficulty, tags, is_unanswerable, None)
        )
    return parsed
