"""文档解析。扫描版 PDF / OCR / 复杂表格明确失败或告警，不假装成功。"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from charset_normalizer import from_bytes
from docx import Document as DocxDocument
from pypdf import PdfReader

from app.core.config import settings
from app.core.exceptions import AppError

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_BLANK_RE = re.compile(r"[ \t]+\n")
_MANY_NL = re.compile(r"\n{3,}")
_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class ExtractedPage:
    page_no: int
    text: str
    heading: str | None = None


@dataclass
class ExtractResult:
    text: str
    pages: list[ExtractedPage] = field(default_factory=list)
    headings: list[str] = field(default_factory=list)
    warning: str | None = None
    parser: str = ""


def sniff_kind(filename: str, payload: bytes) -> str:
    """用魔数校验扩展名，避免把可执行文件改后缀上传。"""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext == "markdown":
        ext = "md"
    if payload.startswith(b"%PDF"):
        kind = "pdf"
    elif payload[:2] == b"PK" and _looks_like_docx(payload):
        kind = "docx"
    else:
        kind = "text"
    if ext == "pdf" and kind != "pdf":
        raise AppError("文件内容不是有效 PDF", code=40073, status_code=400)
    if ext == "docx" and kind != "docx":
        raise AppError("文件内容不是有效 DOCX", code=40073, status_code=400)
    if ext in {"txt", "md"} and kind == "pdf":
        raise AppError("文本扩展名与文件内容不一致", code=40073, status_code=400)
    return ext or kind


def _looks_like_docx(payload: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            return "[Content_Types].xml" in archive.namelist() and any(
                name.startswith("word/") for name in archive.namelist()
            )
    except zipfile.BadZipFile:
        return False


def clean_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    text = _BLANK_RE.sub("\n", text)
    text = _MANY_NL.sub("\n\n", text)
    return text.strip()


def extract_document(filename: str, payload: bytes) -> ExtractResult:
    ext = sniff_kind(filename, payload)
    if ext == "pdf":
        return _extract_pdf(payload)
    if ext == "docx":
        return _extract_docx(payload)
    if ext in {"md", "txt"}:
        return _extract_text(payload, markdown=ext == "md")
    raise AppError("不支持的文件类型", code=40071, status_code=400)


def _extract_pdf(payload: bytes) -> ExtractResult:
    try:
        reader = PdfReader(io.BytesIO(payload))
    except Exception as exc:
        raise AppError(f"PDF 无法打开：{exc}", code=40074, status_code=400) from exc
    pages: list[ExtractedPage] = []
    empty_pages: list[int] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except Exception:
            raw = ""
        text = clean_text(raw)
        if not text:
            empty_pages.append(index)
        pages.append(ExtractedPage(page_no=index, text=text))
    joined = clean_text("\n\n".join(item.text for item in pages if item.text))
    if not joined:
        raise AppError(
            "未能提取到文本，可能是扫描版或图片型 PDF。V2 不支持 OCR，请改用可选中文字的 PDF。",
            code=40075,
            status_code=400,
        )
    warning = None
    if empty_pages:
        warning = f"第 {', '.join(str(item) for item in empty_pages[:20])} 页没有可提取文本；复杂表格与图片 OCR 暂不支持。"
    page_note = pdf_page_warning(len(reader.pages))
    if page_note:
        warning = f"{warning} {page_note}".strip() if warning else page_note
    return ExtractResult(text=joined, pages=pages, warning=warning, parser="pypdf")


def pdf_page_warning(page_count: int) -> str | None:
    """页数过多时只告警。解析仍逐页 extract_text，内存随页数增长，这里不拒绝文件。"""
    limit = int(settings.pdf_page_warn)
    if page_count > limit:
        return f"PDF 共 {page_count} 页，超过建议 {limit} 页。当前没有页数硬限制，大文件会增加解析内存。"
    return None


def _extract_docx(payload: bytes) -> ExtractResult:
    try:
        document = DocxDocument(io.BytesIO(payload))
    except Exception as exc:
        raise AppError(f"DOCX 无法打开：{exc}", code=40074, status_code=400) from exc
    parts: list[str] = []
    headings: list[str] = []
    current_heading: str | None = None
    for paragraph in document.paragraphs:
        text = clean_text(paragraph.text)
        if not text:
            continue
        style = (paragraph.style.name or "") if paragraph.style else ""
        if style.lower().startswith("heading"):
            headings.append(text)
            current_heading = text
            parts.append(text)
        else:
            if current_heading and not parts:
                parts.append(current_heading)
            parts.append(text)
    joined = clean_text("\n\n".join(parts))
    if not joined:
        raise AppError("DOCX 中没有可提取的段落文本", code=40075, status_code=400)
    return ExtractResult(
        text=joined,
        pages=[ExtractedPage(page_no=1, text=joined, heading=headings[0] if headings else None)],
        headings=headings,
        parser="python-docx",
    )


def _extract_text(payload: bytes, *, markdown: bool) -> ExtractResult:
    detected = from_bytes(payload).best()
    if detected is None:
        raise AppError("无法识别文本编码", code=40074, status_code=400)
    raw = str(detected)
    text = clean_text(raw)
    if not text:
        raise AppError("文本文件为空", code=40075, status_code=400)
    headings: list[str] = []
    if markdown:
        for line in text.splitlines():
            match = _MD_HEADING.match(line.strip())
            if match:
                headings.append(match.group(2).strip())
    return ExtractResult(
        text=text,
        pages=[ExtractedPage(page_no=1, text=text, heading=headings[0] if headings else None)],
        headings=headings,
        parser="charset-normalizer",
        warning=None if detected.encoding.lower() in {"utf_8", "utf-8", "utf-8-sig", "ascii", "gb18030", "gbk"} else f"已按 {detected.encoding} 解码",
    )
