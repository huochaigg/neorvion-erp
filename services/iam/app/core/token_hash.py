"""会话标识哈希。Refresh Token 原文不得入库、不得写日志。"""

import hashlib


def hash_token_id(value: str) -> str:
    """对 jti / CSRF 做 SHA-256，仅用于索引与比对。"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
