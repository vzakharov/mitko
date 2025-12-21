# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**IMPORTANT**: Update this file AND README.md whenever making major architectural changes to keep them accurate and in sync.

## Project Overview

Mitko is an LLM-powered Telegram bot that matches IT job seekers with employers through conversational AI and vector-based semantic matching.

## Development Commands

```bash
# Setup
uv sync  # or: pip install -e .
cp .env.example .env  # then edit with credentials
alembic upgrade head

# Run (Development - Long Polling)
python -m src.mitko.main
# Or explicitly:
TELEGRAM_MODE=polling python -m src.mitko.main

# Run (Production - Webhook)
uvicorn src.mitko.main:app --reload --host 0.0.0.0 --port 8000
# Or explicitly:
TELEGRAM_MODE=webhook uvicorn src.mitko.main:app --host 0.0.0.0 --port 8000

# Code quality
black src/ tests/
ruff check src/ tests/
mypy src/
pytest

# Database
alembic revision --autogenerate -m "description"
alembic upgrade head

# Git commits
# Use conventional commit prefixes:
# - feature: new features
# - refactor: code restructuring without behavior change
# - fix: bug fixes
# - docs: documentation changes
# - test: test additions/changes
# - chore: maintenance tasks
#
# Commit when you've completed a self-contained, logical unit of work that:
# - Implements a complete feature or fix
# - Passes basic validation (syntax check, type check if available)
# - Leaves the codebase in a working state
# - Could be meaningfully reviewed or reverted independently
```

## Architecture

**Stack**: FastAPI (webhooks) + aiogram v3 (Telegram) + SQLModel (Pydantic + SQLAlchemy 2.0) async + PostgreSQL/pgvector + APScheduler + PydanticAI

**Flow**: User chats with bot → ConversationAgent handles natural conversation and organically extracts/updates profile → Embedding generated → Background job matches profiles using vector similarity → Both parties accept → Contact details shared

**Key Patterns**:
- Async/await throughout (asyncpg, async sessions)
- SQLModel for Pydantic-powered ORM models with automatic validation
- Unified conversational agent: single PydanticAI agent handles both conversation and profile extraction/updates
- Organic profile creation: no message thresholds, agent decides when it has enough information
- Conversational profile updates: users can modify their profile naturally (e.g., "change my location to Berlin")
- Type-safe validated outputs via Pydantic models (ConversationResponse with utterance + optional profile)
- Automatic retry on invalid LLM responses
- Smart embedding regeneration: only when summary changes, not on every update
- Vector matching: pgvector cosine similarity with configurable threshold
- Two-phase matching: both parties must accept before connection
- Summary-driven matching: all relevant info in text summary (no structured_data field)
- Runtime modes: Webhook (production) or Long Polling (development) - auto-detected or explicit via `TELEGRAM_MODE`

**Structure**:
- `models/`: SQLModel ORM (User with embeddings, Conversation, Match) - Pydantic-powered validation
- `agents/`: PydanticAI agents for structured outputs (ConversationAgent for chat+profiles, RationaleAgent for match explanations)
- `bot/`: Telegram handlers, keyboards, and bot initialization
- `runtime/`: Modular runtime implementations (webhook, polling)
- `llm/`: Provider abstraction (OpenAI/Anthropic) for embeddings
- `services/`: Business logic (profiler with create/update support, matcher)
- `jobs/`: Background matching scheduler

**Important**:
- PostgreSQL requires `pgvector` extension
- Embeddings are 1536-dim vectors (stored in User.embedding)
- Conversation history stored as JSON, full context passed to LLM
- Webhook security via secret token validation
- Match authorization checks required before actions
- **No backwards compatibility needed at this stage** - project hasn't been deployed to production yet
- Models use SQLModel (not pure SQLAlchemy) for Pydantic validation on field assignment
- User model has no `structured_data` field - all info in `summary` for semantic matching
