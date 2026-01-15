"""Populate history for legacy conversations.

Converts PydanticAI-style conversation format (from message_history_json)
to standard message history for conversations without Responses API state.

Revision ID: 019_populate_history_for_legacy
Revises: 018_populate_history
Create Date: 2026-01-15
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from sqlalchemy import text

from alembic import op

revision: str = "019_populate_history_for_legacy"
down_revision: str | None = "018_populate_history"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _convert_pydanticai_to_history(
    message_history_json: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Convert PydanticAI conversation format to standard message history.

    Input format: List of conversation turns with "kind" (request/response)
    and "parts" containing the actual content.

    Output format: List of {"role": "user"|"assistant", "content": "..."}
    """
    messages: list[dict[str, str]] = []

    for turn in message_history_json:
        kind = turn.get("kind")
        parts = turn.get("parts", [])

        if not parts:
            continue

        if kind == "request":
            # Extract user prompts from request parts
            for part in parts:
                part_kind = part.get("part_kind")
                if part_kind == "user-prompt":
                    content = part.get("content", "")
                    if content:
                        messages.append({"role": "user", "content": content})

        elif kind == "response":
            # Extract assistant responses from tool calls
            for part in parts:
                part_kind = part.get("part_kind")
                if part_kind == "tool-call":
                    tool_name = part.get("tool_name")
                    if tool_name == "final_result":
                        args_str = part.get("args", "")
                        if args_str:
                            messages.append(
                                {"role": "assistant", "content": args_str}
                            )

    return messages


def upgrade() -> None:
    connection = op.get_bind()

    # Find conversations without Responses API state
    result = connection.execute(
        text("""
        SELECT id, message_history_json
        FROM conversations
        WHERE last_responses_api_response_id IS NULL
          AND message_history_json IS NOT NULL
          AND message_history_json::text != '[]'
    """)
    )

    rows = result.fetchall()
    if not rows:
        print("No legacy conversations need history population")
        return

    print(f"Found {len(rows)} legacy conversations to populate")

    for row in rows:
        conv_id, message_history_json = row[0], row[1]
        print(f"\nProcessing conversation {conv_id}...")

        try:
            # Parse the PydanticAI format
            pydanticai_history = (
                json.loads(message_history_json)
                if isinstance(message_history_json, str)
                else message_history_json
            )

            # Convert to standard format
            messages = _convert_pydanticai_to_history(pydanticai_history)

            if messages:
                history_json = json.dumps(messages)
                print(
                    f"  Converting {len(messages)} messages ({len(history_json)} bytes)"
                )

                update_result = connection.execute(
                    text("""
                        UPDATE conversations
                        SET history = :history
                        WHERE id = :id
                    """),
                    {"id": str(conv_id), "history": history_json},
                )
                print(f"  Rows updated: {update_result.rowcount}")
            else:
                print("  No messages extracted from history")

        except Exception as e:
            print(f"  Failed: {e}")
            import traceback

            traceback.print_exc()
            continue


def downgrade() -> None:
    # Clear populated history for legacy conversations
    op.execute(
        text("""
        UPDATE conversations
        SET history = '[]'
        WHERE last_responses_api_response_id IS NULL
    """)
    )
