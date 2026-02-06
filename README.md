# Mitko: IT Matchmaker Telegram Bot

An LLM-powered Telegram bot that helps match IT job seekers with employers/contractors through natural conversation.

## Usage

1. Users start a conversation with `/start`
2. Bot asks questions to understand their profile (seeker vs provider)
3. Once profile is complete, bot stores it with vector embeddings
4. Background matching continuously finds matches using:
   - Round-robin fairness (all users tried before retries)
   - Vector similarity search (pgvector cosine distance)
   - Immediate continuation when matches found or rounds exhausted
5. Both parties are notified and can accept/reject
6. When both accept, contact details are shared

## Features

- Natural freeform conversation to understand user profiles
- Unified conversational agent handles both chat and profile extraction/updates
- Organic profile creation - agent decides when it has enough information
- Conversational profile updates (e.g., "change my location to Berlin")
- Automatic profile extraction with vector embeddings
- Smart matching using similarity search (pgvector)
- Mutual consent flow for connections
- Configurable LLM providers (OpenAI/Anthropic)
- Type-safe structured outputs via PydanticAI and Pydantic models
- Multi-language support (EN/RU) with type-safe i18n

## Architecture Diagrams

### Overall System Flow

High-level flow from user interaction through profile creation, matching, and contact sharing.

```mermaid
graph TB
    A[User sends message] --> B[ConversationAgent]
    B --> C{Profile complete?}
    C -->|No| D[Continue conversation]
    C -->|Yes| E[Generate embedding<br/>from matching_summary]
    E --> F[User marked active]
    F --> G[Matching Scheduler Loop]

    G --> H[MatcherService finds<br/>similar user]
    H --> I[RationaleAgent generates<br/>match explanation]
    I --> J[Both users notified]

    J --> K{User A accepts?}
    K -->|Yes| L{User B accepts?}
    K -->|No| M[Match rejected]
    L -->|Yes| N[Contact details shared]
    L -->|No| M

    D --> A
    M --> G
    N --> G
```

### Round-Robin Matching Scheduler

Shows the three possible outcomes in each iteration of the matching loop - the trickiest part of the system.

```mermaid
flowchart TD
    Start([Matching Loop Starts]) --> GetRound[Get current_round from DB]
    GetRound --> FindUserA{Find next user_a<br/>not tried in round}

    FindUserA -->|Found| FindUserB[Search for similar user_b<br/>via vector similarity]
    FindUserB --> CheckUserB{user_b found?}

    CheckUserB -->|Yes| CreateMatch[Create Match<br/>status=pending<br/>matching_round=N]
    CreateMatch --> CreateGen[Create Generation<br/>for rationale]
    CreateGen --> Exit([EXIT - Wait for processor])

    CheckUserB -->|No| CreateUnmatched[Create Match<br/>status=unmatched<br/>user_b_id=NULL]
    CreateUnmatched --> Continue1[Continue same round]
    Continue1 --> FindUserA

    FindUserA -->|None| RoundExhausted[All users tried<br/>in current round]
    RoundExhausted --> AdvanceRound[Increment round:<br/>round = round + 1]
    AdvanceRound --> Continue2[Continue with new round]
    Continue2 --> FindUserA

    FindUserA -->|No complete users| AllMatched[No active users<br/>in system]
    AllMatched --> Sleep[Sleep 30 minutes]
    Sleep --> Start
```

### Match Status State Machine

Shows all possible state transitions during mutual consent flow.

```mermaid
stateDiagram-v2
    [*] --> pending: Match created

    pending --> a_accepted: User A accepts
    pending --> b_accepted: User B accepts
    pending --> rejected: Either rejects

    a_accepted --> connected: User B accepts
    a_accepted --> rejected: User B rejects

    b_accepted --> connected: User A accepts
    b_accepted --> rejected: User A rejects

    connected --> [*]: Contact details shared
    rejected --> [*]: Match closed
```

### Generation Orchestration

Shows how GenerationOrchestrator manages all types of LLM generations with budget control - a universal queueing system.

```mermaid
flowchart TB
    subgraph Sources["Generation Sources"]
        MsgHandler[Message Handler]
        MatchSched[Matching Scheduler]
        Future[Future Agents...]
    end

    subgraph Orchestrator["GenerationOrchestrator"]
        CreateGen[create_generation]
        CalcInterval[Calculate interval:<br/>cost × 604800s / weekly_budget]
        GetMaxSched[Get max scheduled_for<br/>from all generations]
        Schedule[scheduled_for =<br/>max_scheduled + interval]
    end

    subgraph Queue["Generation Queue<br/>(Database)"]
        PendingGens[(Pending Generations<br/>sorted by scheduled_for)]
    end

    subgraph Processor["Generation Processor Loop"]
        GetNext[Get next generation<br/>where scheduled_for ≤ now]
        ExecType{Type?}
        ConvExec[ConversationGeneration.execute]
        MatchExec[MatchGeneration.execute]
        RecordCost[Record cost_usd]
    end

    MsgHandler --> CreateGen
    MatchSched --> CreateGen
    Future --> CreateGen

    CreateGen --> CalcInterval
    CalcInterval --> GetMaxSched
    GetMaxSched --> Schedule
    Schedule --> PendingGens

    PendingGens --> GetNext
    GetNext --> ExecType
    ExecType -->|conversation_id| ConvExec
    ExecType -->|match_id| MatchExec
    ConvExec --> RecordCost
    MatchExec --> RecordCost
    RecordCost -.affects next interval.-> CalcInterval

    style Orchestrator fill:#e1f5ff
    style Processor fill:#fff4e1
```

### Budget Control Formula

Shows the dynamic spacing calculation in detail.

```mermaid
graph LR
    A[Last generation cost:<br/>$0.01] --> B[Weekly budget:<br/>$6.00]
    B --> C[Calculate:<br/>0.01 × 604800s / 6.00]
    C --> D[Interval:<br/>~1008 seconds<br/>≈17 minutes]
    D --> E[Next generation<br/>scheduled at:<br/>max_scheduled + 17min]

    style A fill:#ffebe9
    style B fill:#e1f5ff
    style C fill:#fff4e1
    style D fill:#e7f5e1
    style E fill:#f5e1ff
```

## Architecture

- **FastAPI** - Web framework for webhook handling
- **aiogram v3** - Async Telegram bot framework
- **SQLModel** - Pydantic-powered async ORM (built on SQLAlchemy 2.0)
- **PydanticAI** - Type-safe LLM agent framework with structured outputs
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
- `MITKO_LANGUAGE` - Language for bot responses: `en` or `ru` (default: `en`)
- `MATCHING_INTERVAL_MINUTES` - How often to run matching (default: 30)
- `SIMILARITY_THRESHOLD` - Minimum similarity score for matches (default: 0.7)
- `MAX_MATCHES_PER_PROFILE` - Max matches per profile per run (default: 5)
- `WEEKLY_BUDGET_USD` - Target weekly LLM spending in USD (default: 6.0). See Budget Control section below.

## Budget Control

The bot uses dynamic cost-based scheduling to stay within a weekly LLM budget. When a user sends a message, the system calculates how long to wait before processing it based on the cost of the previous generation.

**How it works**:
- The interval between generations is proportional to the last generation's cost
- Formula: if the last generation cost X dollars, wait `(X / weekly_budget) * 1 week` before the next one
- Example: With a $6/week budget, a $0.01 generation schedules the next one ~17 minutes later
- The system self-adjusts: expensive conversations (long chat histories) automatically increase spacing
- First generation always runs immediately since there's no cost history yet

This ensures spending stays roughly constant week-to-week regardless of conversation complexity. Currently applies to the conversation agent; rationale agent integration planned once APIs are unified.

## Development

The project uses:
- Type hints throughout
- Async/await for all I/O operations
- SQLModel (Pydantic + SQLAlchemy 2.0) async patterns
- PydanticAI for type-safe LLM agent outputs
- Pydantic models for validation and structured data
- Single unified ConversationAgent for natural conversation and profile management
- Type-safe i18n with nested dataclasses for full IDE autocomplete

