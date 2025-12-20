# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
```

## Architecture

**Stack**: FastAPI (webhooks) + aiogram v3 (Telegram) + SQLAlchemy 2.0 async + PostgreSQL/pgvector + APScheduler

**Flow**: User chats with bot → LLM extracts profile → Embedding generated → Background job matches profiles using vector similarity → Both parties accept → Contact details shared

**Key Patterns**:
- Async/await throughout (asyncpg, async sessions)
- SQLAlchemy 2.0 with `Mapped[]` type hints
- LLM provider abstraction via Protocol (swappable OpenAI/Anthropic)
- Profile extraction: LLM returns `<PROFILE_COMPLETE>` token + JSON when ready
- Vector matching: pgvector cosine similarity with configurable threshold
- Two-phase matching: both parties must accept before connection
- Runtime modes: Webhook (production) or Long Polling (development) - auto-detected or explicit via `TELEGRAM_MODE`

**Structure**:
- `models/`: SQLAlchemy ORM (User, Profile with embeddings, Conversation, Match)
- `bot/`: Telegram handlers, keyboards, and bot initialization
- `runtime/`: Modular runtime implementations (webhook, polling)
- `llm/`: Provider abstraction (OpenAI/Anthropic)
- `services/`: Business logic (profiler, matcher)
- `jobs/`: Background matching scheduler

**Important**:
- PostgreSQL requires `pgvector` extension
- Embeddings are 1536-dim vectors
- Conversation history stored as JSON, full context passed to LLM
- Webhook security via secret token validation
- Match authorization checks required before actions
- **No backwards compatibility needed at this stage** - project hasn't been deployed to production yet
