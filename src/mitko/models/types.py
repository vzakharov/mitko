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

        decoded_value = value.decode("utf-8")

        return (
            json.loads(decoded_value)
            if dialect.name == "postgresql"
            else decoded_value
        )

    def process_result_value(self, value: Any, dialect: Dialect):
        """Convert database value to Python bytes.

        Args:
            value: Value from database
            dialect: SQLAlchemy dialect object

        Returns:
            Bytes representation of the value
        """

        return (
            value
            if isinstance(value, bytes) or value is None
            else (
                value if isinstance(value, str) else json.dumps(value)
            ).encode("utf-8")
        )
