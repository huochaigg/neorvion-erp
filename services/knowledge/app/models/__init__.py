"""ORM 模型。Alembic 通过导入本包收集 metadata。"""

from app.db.base import Base
from app.models.knowledge import (
    KnowledgeBase,
    KnowledgeBaseStatus,
    KnowledgeDocument,
    KnowledgeDocumentStatus,
)

__all__ = [
    "Base",
    "KnowledgeBase",
    "KnowledgeBaseStatus",
    "KnowledgeDocument",
    "KnowledgeDocumentStatus",
]
