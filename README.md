# Mitko: IT Matchmaker Telegram Bot

An LLM-powered Telegram bot that helps match IT job seekers with employers/contractors through natural conversation.

## Usage

1. Users start a conversation with `/start`
2. Bot asks questions to understand their profile (seeker vs provider)
3. Once profile is complete, bot stores it with vector embeddings
4. Background job periodically finds matches using cosine similarity
5. Both parties are notified and can accept/reject
6. When both accept, contact details are shared

## Features

- Freeform conversation to understand user profiles
- Automatic profile extraction and vector embeddings
- Smart matching using similarity search (pgvector)
- Mutual consent flow for connections
- Configurable LLM providers (OpenAI/Anthropic)

## Architecture

- **FastAPI** - Web framework for webhook handling
- **aiogram v3** - Async Telegram bot framework
- **SQLAlchemy 2.0** - Async ORM
- **Neon PostgreSQL + pgvector** - Database with vector similarity search
- **APScheduler** - Background job scheduling for matching

## Setup

1. Install dependencies:
```bash
uv sync
# or
pip install -e .
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your credentials
```

3. Set up database with pgvector extension:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

4. Run migrations:
```bash
alembic upgrade head
```

5. Start the bot:
```bash
uvicorn src.mitko.main:app --reload --host 0.0.0.0 --port 8000
```

6. Set webhook URL (replace with your domain):
```bash
curl -X POST "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/setWebhook?url=https://your-domain.com/webhook/your_secret"
```

## Environment Variables

- `DATABASE_URL` - PostgreSQL connection string (postgresql+asyncpg://...)
- `TELEGRAM_BOT_TOKEN` - Telegram bot token from @BotFather
- `TELEGRAM_WEBHOOK_SECRET` - Secret for webhook validation
- `TELEGRAM_WEBHOOK_URL` - Full webhook URL (optional, for auto-setup)
- `LLM_PROVIDER` - `openai` or `anthropic` (default: `openai`)
- `OPENAI_API_KEY` - OpenAI API key (required if using OpenAI)
- `ANTHROPIC_API_KEY` - Anthropic API key (required if using Anthropic)
- `MATCHING_INTERVAL_MINUTES` - How often to run matching (default: 30)
- `SIMILARITY_THRESHOLD` - Minimum similarity score for matches (default: 0.7)
- `MAX_MATCHES_PER_PROFILE` - Max matches per profile per run (default: 5)

## Development

The project uses:
- Type hints throughout
- Async/await for all I/O operations
- SQLAlchemy 2.0 async patterns
- Pydantic for configuration validation

