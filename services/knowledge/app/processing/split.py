"""切片。长度单位是字符（Python len），不是 Token。"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter

from app.core.config import settings
from app.core.exceptions import AppError
from app.models.knowledge import ChunkStrategy

CHINESE_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""]


@dataclass
class ChunkDraft:
    index: int
    content: str
    char_count: int
    source_start: int
    source_end: int
    page_no: int | None
    heading: str | None


def validate_chunk_params(strategy: str, chunk_size: int, chunk_overlap: int) -> tuple[str, int, int]:
    normalized = strategy.strip().upper()
    if normalized not in {ChunkStrategy.FIXED.value, ChunkStrategy.RECURSIVE.value}:
        raise AppError("切片策略不合法", code=40076, status_code=400)
    if chunk_size < settings.chunk_size_min or chunk_size > settings.chunk_size_max:
        raise AppError(
            f"切片长度须在 {settings.chunk_size_min}-{settings.chunk_size_max} 字符之间",
            code=40076,
            status_code=400,
        )
    if chunk_overlap < 0 or chunk_overlap >= chunk_size:
        raise AppError("重叠长度必须小于切片长度，且不能为负数", code=40076, status_code=400)
    return normalized, chunk_size, chunk_overlap


def split_text(
    text: str,
    *,
    strategy: str,
    chunk_size: int,
    chunk_overlap: int,
    pages: list[dict] | None = None,
    headings: list[str] | None = None,
) -> list[ChunkDraft]:
    """按字符切分，并尽量回填页码 / 标题。"""
    strategy, chunk_size, chunk_overlap = validate_chunk_params(strategy, chunk_size, chunk_overlap)
    cleaned = text.strip()
    if not cleaned:
        raise AppError("没有可切片的文本，请先成功解析文档", code=40077, status_code=400)
    if strategy == ChunkStrategy.FIXED.value:
        splitter = CharacterTextSplitter(
            separator="",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )
    else:
        splitter = RecursiveCharacterTextSplitter(
            separators=CHINESE_SEPARATORS,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
        )
    pieces = [item.strip() for item in splitter.split_text(cleaned) if item.strip()]
    drafts: list[ChunkDraft] = []
    cursor = 0
    heading = headings[0] if headings else None
    for index, piece in enumerate(pieces):
        start = cleaned.find(piece, cursor)
        if start < 0:
            start = cursor
        end = start + len(piece)
        drafts.append(
            ChunkDraft(
                index=index,
                content=piece,
                char_count=len(piece),
                source_start=start,
                source_end=end,
                page_no=_page_for_offset(pages, start),
                heading=heading,
            )
        )
        cursor = end
    return drafts


def _page_for_offset(pages: list[dict] | None, offset: int) -> int | None:
    if not pages:
        return None
    consumed = 0
    for page in pages:
        text = str(page.get("text") or "")
        length = len(text)
        if offset <= consumed + length:
            return int(page.get("page_no") or 0) or None
        consumed += length + 2
    last = pages[-1].get("page_no")
    return int(last) if last else None
