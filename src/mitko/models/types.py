"""Custom SQLAlchemy types for cross-database compatibility"""

import json
from typing import Any, cast

from pydantic import HttpUrl
from sqlalchemy import Dialect, Text, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import String


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


class JSONBList(TypeDecorator[list[Any]]):
    """JSONB type for list data that works with both PostgreSQL and SQLite.

    - PostgreSQL: Uses native JSONB type for efficient JSON storage and querying
    - SQLite: Falls back to Text with automatic encoding/decoding

    Stores data as list[dict] in Python, handling serialization automatically.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        """Select appropriate type based on database dialect.

        Args:
            dialect: SQLAlchemy dialect object

        Returns:
            Type descriptor appropriate for the dialect
        """
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(
        self, value: list[Any] | None, dialect: Dialect
    ) -> list[Any] | str | None:
        """Convert Python list to database format.

        Args:
            value: List value from Python
            dialect: SQLAlchemy dialect object

        Returns:
            Value in appropriate format for the database
        """
        if value is None:
            return None

        return value if dialect.name == "postgresql" else json.dumps(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> list[Any]:
        """Convert database value to Python list.

        Args:
            value: Value from database
            dialect: SQLAlchemy dialect object

        Returns:
            List representation of the value
        """
        if value is None:
            return []

        if isinstance(value, list):
            return cast(list[Any], value)

        if isinstance(value, str):
            return json.loads(value)

        return value


class HttpUrlType(TypeDecorator[Any]):
    """Custom SQLAlchemy type for Pydantic HttpUrl validation.

    Stores URLs as strings in the database while providing Pydantic validation
    in Python layer. Supports nullable URLs.
    """

    impl = String(2083)  # Max URL length
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
        """Convert HttpUrl to string for database storage.

        Args:
            value: HttpUrl instance from Python
            dialect: SQLAlchemy dialect object

        Returns:
            String representation of URL or None
        """
        return str(value) if value is not None else None

    def process_result_value(
        self, value: Any, dialect: Dialect
    ) -> HttpUrl | None:
        """Convert string from database to HttpUrl.

        Args:
            value: String value from database
            dialect: SQLAlchemy dialect object

        Returns:
            HttpUrl instance or None
        """
        return HttpUrl(url=value) if value is not None else None
