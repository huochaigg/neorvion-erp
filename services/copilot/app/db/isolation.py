from neorvion_db import build_registry

import app.models  # noqa: F401
from app.db.base import Base

REGISTRY = build_registry(Base, {})
