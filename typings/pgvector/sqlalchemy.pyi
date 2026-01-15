# Type stubs for pgvector.sqlalchemy
# Minimal stubs covering our usage of Vector type

from typing import Any

from sqlalchemy.types import UserDefinedType

class Vector(UserDefinedType[list[float]]):
    """Vector type for pgvector extension."""

    def __init__(self, dim: int | None = None) -> None: ...
    def get_col_spec(self, **kwargs: Any) -> str: ...
    def bind_processor(self, dialect: Any) -> Any: ...
    def result_processor(self, dialect: Any, coltype: Any) -> Any: ...
