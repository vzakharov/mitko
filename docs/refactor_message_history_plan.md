# Plan: Responses API Fallback with Conversation History

## Problem
1. OpenAI Responses API stores conversation state server-side, referenced by `previous_response_id`
2. Responses expire after 30 days - no fallback exists
3. `all_messages_json` from Responses API only includes most recent exchange + previous_response_id

## Solution
Store conversation history as JSON in DB, inject as formatted text into agent instructions when Responses API state expires.

---

## Implementation Steps

### 1. Add Type Definition
**File:** `src/mitko/types/messages.py`

Add `HistoryMessage` TypedDict:
```python
class HistoryMessage(TypedDict):
    role: Literal["user", "assistant"]
    content: str
```

### 2. Add Database Field
**File:** `src/mitko/models/conversation.py`

Add `history` field (typed as `list[HistoryMessage]`):
- Use native JSONB (not SQLiteReadyJSONB since pgvector is PostgreSQL-only)
- Default to empty list `[]`

### 3. Create Schema Migration
```bash
uv run alembic revision --autogenerate -m "add history"
```
Rename to `017_add_history.py`

### 4. Create Data Migration
**File:** `alembic/versions/018_populate_history.py` (manual migration)

For conversations with `last_responses_api_response_id`:
- Use `AsyncOpenAI.responses.retrieve(response_id)` to fetch response
- Walk backwards through chain via `previous_response_id` field on response
- Build history in chronological order
- Handle errors gracefully (skip conversations where response is gone)
- Handle rate limits with backoff

### 5. Add Helper Functions in generation.py
**File:** `src/mitko/jobs/generation.py`

```python
def _format_history_for_instructions(history: list[HistoryMessage]) -> str:
    """Format history as readable text for instructions injection."""
    # Include truncation for very long conversations

def _is_expired_response_error(error: ModelHTTPError) -> bool:
    """Check if error indicates expired/missing response."""
    # Known patterns from OpenAI:
    # - HTTP 400 with "Container is expired" or "not found" in body
    # - HTTP 404 (NotFoundError)
    # Be conservative: only match these specific patterns
```

### 6. Update LLM Call Logic with Fallback
**File:** `src/mitko/jobs/generation.py`

Current flow (lines 153-180):
```
if use_responses_api:
    if has_previous_response_id:
        call with previous_response_id, message_history=None
    else:
        call with message_history from DB
else:
    call with message_history from DB
```

New flow:
```
if use_responses_api:
    if has_previous_response_id:
        try:
            call with previous_response_id, message_history=None
        except ModelHTTPError as e:
            if _is_expired_response_error(e):
                log warning with specific error details
                clear last_responses_api_response_id
                FALLBACK: call again with history injected into instructions
            else:
                raise  # re-raise unrelated errors
    else:
        # First message OR after fallback cleared the ID
        call normally (inject history into instructions if available)
else:
    call with message_history from DB
```

**Instructions injection:** Pass `instructions` parameter to `Agent.run()` with:
```python
instructions=CONVERSATION_AGENT.instructions + "\n\n" + _format_history_for_instructions(conv.history)
```
This preserves original instructions and appends history at the end.

### 7. Update History After Each LLM Call
**File:** `src/mitko/jobs/generation.py`

After successful `CONVERSATION_AGENT.run()`:
```python
conv.history = [
    *conv.history,
    {"role": "user", "content": user_prompt},
    {"role": "assistant", "content": response.utterance},
]
```

### 8. Update Reset Functions
**Files:**
- `src/mitko/bot/handlers.py` - `reset_conversation_state()`
- `src/mitko/services/profiler.py` - `ProfileService.reset_profile()`

Add: `conversation.history = []`

### 9. Update CLAUDE.md
**File:** `CLAUDE.md`

Remove line ~119:
```
- **No backwards compatibility needed at this stage** - project hasn't been deployed to production yet
```

---

## Files to Modify
1. `src/mitko/types/messages.py` - Add HistoryMessage type
2. `src/mitko/models/conversation.py` - Add history field
3. `alembic/versions/017_add_history.py` - Schema migration (autogenerate)
4. `alembic/versions/018_populate_history.py` - Data migration (manual)
5. `src/mitko/jobs/generation.py` - Fallback logic + history updates
6. `src/mitko/bot/handlers.py` - Reset function update
7. `src/mitko/services/profiler.py` - Reset function update
8. `CLAUDE.md` - Remove backwards compat note

---

## Future Phase (after manual verification)
- Migration `019_drop_message_history_json.py` - Drop old field
- Update all references to remove `message_history_json`

---

## Verification
1. Run `uv run alembic upgrade head` to apply migrations
2. Manually inspect populated `history` for existing conversations
3. Test fallback by temporarily clearing `last_responses_api_response_id` for a conversation and sending a message
4. Verify conversation continues with history context
5. Run `uv run pyright` and `uv run pytest`
