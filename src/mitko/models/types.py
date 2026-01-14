"""Custom SQLAlchemy types for cross-database compatibility"""

import json
from typing import Any

from sqlalchemy import Dialect, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB


class SQLiteReadyJSONB(TypeDecorator[bytes]):
    """JSONB type that works with both PostgreSQL and SQLite.

    - PostgreSQL: Uses native JSONB type for efficient JSON storage and querying
    - SQLite: Falls back to Text with automatic encoding/decoding

    Stores data as bytes in Python, ensuring consistent interface across dialects.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect):
        """Select appropriate type based on database dialect.

        Args:
            dialect: SQLAlchemy dialect object

        Returns:
            Type descriptor appropriate for the dialect
        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value: bytes | None, dialect: Dialect):
        """Convert Python bytes to database format.

        Args:
            value: Bytes value from Python
            dialect: SQLAlchemy dialect object

        Returns:
            Value in appropriate format for the database
        """
        if value is None:
            return None

        if dialect.name == "postgresql":
            # PostgreSQL JSONB expects a Python object (list/dict)
            # Deserialize bytes → Python object
            return json.loads(value.decode("utf-8"))

        # SQLite: decode bytes to string
        return value.decode("utf-8")

    def process_result_value(self, value: Any, dialect: Dialect):
        """Convert database value to Python bytes.

        Args:
            value: Value from database
            dialect: SQLAlchemy dialect object

        Returns:
            Bytes representation of the value
        """
        if value is None:
            return None

        if isinstance(value, bytes):
            # PostgreSQL returns bytes
            return value

        if isinstance(value, str):
            # SQLite returns string, encode to bytes
            return value.encode("utf-8")

        # Fallback: convert to string first, then bytes
        return str(value).encode("utf-8")
