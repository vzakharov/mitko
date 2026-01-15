"""Populate history for existing conversations.

Fetches conversation history from OpenAI Responses API for conversations
that have last_responses_api_response_id set.

Revision ID: 018_populate_history
Revises: 6264e8b27c23
Create Date: 2026-01-15
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from collections.abc import Sequence
from typing import TYPE_CHECKING

from openai import AsyncOpenAI, NotFoundError, RateLimitError
from openai.types.responses import (
    ResponseFunctionToolCallItem,
    ResponseInputMessageItem,
    ResponseInputText,
    ResponseItem,
    ResponseOutputMessage,
    ResponseOutputText,
)
from sqlalchemy import text

from alembic import op

if TYPE_CHECKING:
    from openai.types.responses import Response

revision: str = "018_populate_history"
down_revision: str | None = "6264e8b27c23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


async def _fetch_response_chain(
    client: AsyncOpenAI, response_id: str
) -> list[dict[str, str]]:
    """Fetch conversation history from Responses API.

    The input items list contains the full conversation history in reverse order.
    """
    print(f"  Fetching response {response_id}...")
    try:
        response: Response = await client.responses.retrieve(response_id)
    except NotFoundError:
        print(f"  Response {response_id} not found")
        return []
    except RateLimitError:
        print("  Rate limited, waiting 5s...")
        time.sleep(5)
        return await _fetch_response_chain(client, response_id)
    except Exception as e:
        print(f"  Error fetching response {response_id}: {e}")
        return []

    messages: list[dict[str, str]] = []

    # Get current assistant response text
    assistant_text = response.output_text or "\n\n".join(
        "\n\n".join(
            [
                part.text
                for part in item.content
                if isinstance(part, ResponseOutputText)
            ]
        )
        for item in response.output
        if isinstance(item, ResponseOutputMessage)
    )
    print(f"  Assistant text: {assistant_text[:50]}...")

    # Get input items (full conversation history in reverse chronological order)
    print(f"  Fetching input items for response {response_id}")
    input_items_response = await client.responses.input_items.list(
        response_id, limit=100
    )
    print(f"  Input items response: {input_items_response}")
    input_items_list = [item for item in input_items_response]

    # Extract the data tuple from the list (format: [('data', [...]), ('has_more', False), ...])
    input_items_data: list[ResponseItem] = []
    for item in input_items_list:
        if item[0] == "data":
            input_items_data = item[1]
            break

    print(f"  Got {len(input_items_data)} history items")

    # Reverse to get chronological order (oldest first)
    for item in reversed(input_items_data):
        if isinstance(item, ResponseInputMessageItem):
            # User message
            text_parts = [
                part.text
                for part in item.content or []
                if isinstance(part, ResponseInputText)
            ]
            if text_parts:
                content = "\n\n".join(text_parts)
                messages.append({"role": "user", "content": content})
                print(f"    Added user message: {content[:50]}...")

        elif isinstance(item, ResponseOutputMessage):
            # Assistant message from history
            text_parts = [
                part.text
                for part in item.content or []
                if isinstance(part, ResponseOutputText)
            ]
            if text_parts:
                content = "\n\n".join(text_parts)
                messages.append({"role": "assistant", "content": content})
                print(f"    Added assistant message: {content[:50]}...")

        elif isinstance(item, ResponseFunctionToolCallItem):
            content = item.arguments
            messages.append({"role": "assistant", "content": content})
            print(f"    Added function call: {content[:50]}...")

        else:
            print(f"    Skipping {type(item).__name__}")
            continue

    # Add current assistant response at the end
    if assistant_text:
        messages.append({"role": "assistant", "content": assistant_text})
        print(f"  Added current response: {assistant_text[:50]}...")

    print(f"  Total messages: {len(messages)}")
    return messages


def upgrade() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("WARNING: OPENAI_API_KEY not set, skipping history population")
        return

    connection = op.get_bind()

    # Find conversations with Responses API state to populate
    result = connection.execute(
        text("""
        SELECT id, last_responses_api_response_id
        FROM conversations
        WHERE last_responses_api_response_id IS NOT NULL
    """)
    )

    rows = result.fetchall()
    if not rows:
        print("No conversations need history population")
        return

    print(f"Found {len(rows)} conversations to populate")

    client = AsyncOpenAI(api_key=api_key)

    # Store results to write to DB in main thread
    results: dict[str, str] = {}

    async def fetch_all() -> None:
        """Fetch all message histories from OpenAI API."""
        for row in rows:
            conv_id, response_id = row[0], row[1]
            print(
                f"\nProcessing conversation {conv_id} with response_id {response_id}..."
            )
            try:
                messages = await _fetch_response_chain(client, response_id)
                if messages:
                    history_json = json.dumps(messages)
                    print(
                        f"  Fetched {len(messages)} messages ({len(history_json)} bytes)"
                    )
                    results[str(conv_id)] = history_json
                else:
                    print("  No messages found (response may have expired)")
            except Exception as e:
                print(f"  Failed: {e}")
                import traceback

                traceback.print_exc()
                continue

    # Run async code in a new thread with its own event loop
    # (can't use existing loop - it's running in a greenlet context)
    def run_in_thread():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            new_loop.run_until_complete(fetch_all())
        finally:
            new_loop.close()

    thread = threading.Thread(target=run_in_thread)
    thread.start()
    thread.join()

    # Now write results to database in main thread
    for conv_id, history_json in results.items():
        print(f"Writing to database: conversation {conv_id}...")
        result = connection.execute(
            text("""
                UPDATE conversations
                SET history = :history
                WHERE id = :id
            """),
            {"id": conv_id, "history": history_json},
        )
        print(f"  Rows updated: {result.rowcount}")


def downgrade() -> None:
    # Clear populated history data
    op.execute(text("UPDATE conversations SET history = '[]'"))
