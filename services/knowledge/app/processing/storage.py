"""本地磁盘存储。路径全部相对于 storage_root，禁止目录穿越。"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AppError

_SAFE_EXT = {"pdf", "docx", "txt", "md"}
_FILENAME_RE = re.compile(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+")


def storage_root() -> Path:
    root = Path(settings.storage_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def sanitize_filename(name: str) -> str:
    raw = Path(name.replace("\\", "/")).name.strip()
    if not raw or raw in {".", ".."}:
        return "unnamed"
    cleaned = _FILENAME_RE.sub("_", raw).strip("._") or "unnamed"
    return cleaned[:180]


def normalize_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix == "markdown":
        suffix = "md"
    return suffix


def ensure_allowed_extension(filename: str) -> str:
    ext = normalize_extension(filename)
    if ext not in _SAFE_EXT:
        raise AppError("仅支持 PDF、DOCX、TXT、Markdown", code=40071, status_code=400)
    return ext


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def document_dir(tenant_id: int, knowledge_base_id: int, document_id: int) -> Path:
    path = storage_root() / str(tenant_id) / str(knowledge_base_id) / str(document_id)
    resolved = path.resolve()
    if not resolved.is_relative_to(storage_root()):
        raise AppError("非法存储路径", code=40072, status_code=400)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def build_storage_key(tenant_id: int, knowledge_base_id: int, document_id: int, ext: str) -> str:
    return f"{tenant_id}/{knowledge_base_id}/{document_id}/original.{ext}"


def resolve_stored_path(storage_key: str) -> Path:
    """把相对键解析为绝对路径，拒绝跳出存储根。"""
    if not storage_key or storage_key.startswith("/") or "\\" in storage_key or ".." in storage_key:
        raise AppError("非法存储路径", code=40072, status_code=400)
    resolved = (storage_root() / storage_key).resolve()
    if not resolved.is_relative_to(storage_root()):
        raise AppError("非法存储路径", code=40072, status_code=400)
    return resolved


def write_bytes(storage_key: str, payload: bytes) -> None:
    path = resolve_stored_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def read_bytes(storage_key: str) -> bytes:
    path = resolve_stored_path(storage_key)
    if not path.is_file():
        raise AppError("原文件不存在或已被清理", code=40452, status_code=404)
    return path.read_bytes()


def delete_document_files(tenant_id: int, knowledge_base_id: int, document_id: int) -> None:
    directory = document_dir(tenant_id, knowledge_base_id, document_id)
    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.is_file():
            child.unlink()
    try:
        directory.rmdir()
    except OSError:
        pass
