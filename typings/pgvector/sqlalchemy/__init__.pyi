from typing import Any

# Return Any so SQLAlchemy mapped_column accepts Vector(dim) under type checking.
def Vector(dim: int | None = None) -> Any: ...
def VECTOR(dim: int | None = None) -> Any: ...

__all__ = ["Vector", "VECTOR"]
