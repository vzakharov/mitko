---
name: Mitko IT Matchmaker Bot
overview: Build a Telegram bot that profiles IT job seekers and employers through freeform conversation, stores vector embeddings of profiles, and automatically matches compatible parties using similarity search.
todos:
  - id: project-setup
    content: Initialize project with uv, pyproject.toml, and folder structure
    status: pending
  - id: config-settings
    content: Create pydantic-settings config for env vars (DB, Telegram, LLM keys)
    status: pending
  - id: db-models
    content: Define SQLAlchemy models for users, conversations, profiles, matches
    status: pending
  - id: alembic-setup
    content: Set up Alembic migrations with pgvector extension
    status: pending
  - id: llm-abstraction
    content: Build LLM provider abstraction (OpenAI + Anthropic implementations)
    status: pending
  - id: telegram-webhook
    content: Set up FastAPI webhook endpoint + aiogram bot dispatcher
    status: pending
  - id: conversation-engine
    content: Implement conversation state machine and message handling
    status: pending
  - id: profile-extraction
    content: Build profile generator that extracts structured data + summary from conversation
    status: pending
  - id: embedding-service
    content: Implement embedding generation and storage with pgvector
    status: pending
  - id: matching-job
    content: Create matching cron job with similarity search queries
    status: pending
  - id: match-notifications
    content: Build notification system with inline keyboards for consent
    status: pending
  - id: connection-handler
    content: Handle mutual acceptance and contact detail sharing
    status: pending
---

# Mitko: IT Matchmaker Telegram Bot

## Architecture Overview

```mermaid
flowchart TB
    subgraph telegram [Telegram]
        User[User]
    end
    
    subgraph app [FastAPI Application]
        Webhook[Webhook Handler]
        ConvEngine[Conversation Engine]
        LLMLayer[LLM Abstraction Layer]
        ProfileGen[Profile Generator]
        MatchNotifier[Match Notifier]
    end
    
    subgraph storage [Neon PostgreSQL]
        Users[(users)]
        Conversations[(conversations)]
        Profiles[(profiles + pgvector)]
        Matches[(matches)]
    end
    
    subgraph jobs [Background Jobs]
        MatchingCron[Matching Cron Job]
    end
    
    User <-->|messages| Webhook
    Webhook --> ConvEngine
    ConvEngine <--> LLMLayer
    ConvEngine --> ProfileGen
    ProfileGen --> Profiles
    MatchingCron --> Profiles
    MatchingCron --> Matches
    Matches --> MatchNotifier
    MatchNotifier -->|notifications| User
```

## Project Structure

```
mitko/
├── pyproject.toml              # Dependencies (poetry/uv)
├── alembic/                    # DB migrations
│   └── versions/
├── src/
│   └── mitko/
│       ├── __init__.py
│       ├── main.py             # FastAPI app + webhook
│       ├── config.py           # Settings via pydantic-settings
│       ├── models/             # SQLAlchemy models
│       │   ├── __init__.py
│       │   ├── user.py
│       │   ├── conversation.py
│       │   ├── profile.py
│       │   └── match.py
│       ├── llm/                # LLM abstraction layer
│       │   ├── __init__.py
│       │   ├── base.py         # Abstract base class
│       │   ├── openai.py
│       │   ├── anthropic.py
│       │   └── embeddings.py   # Embedding generation
│       ├── bot/                # Telegram bot logic
│       │   ├── __init__.py
│       │   ├── handlers.py     # Message handlers
│       │   ├── keyboards.py    # Inline keyboards
│       │   └── conversation.py # Conversation state machine
│       ├── services/           # Business logic
│       │   ├── __init__.py
│       │   ├── profiler.py     # Profile extraction
│       │   └── matcher.py      # Matching engine
│       └── jobs/               # Background tasks
│           ├── __init__.py
│           └── matching.py     # Cron job for matching
├── tests/
└── README.md
```

## Database Schema

```mermaid
erDiagram
    users ||--o{ conversations : has
    users ||--o| profiles : has
    profiles ||--o{ matches : involved_in
    
    users {
        bigint telegram_id PK
        string role "seeker|provider"
        string state "onboarding|profiling|active|paused"
        timestamp created_at
    }
    
    conversations {
        uuid id PK
        bigint telegram_id FK
        jsonb messages "array of role+content"
        timestamp updated_at
    }
    
    profiles {
        uuid id PK
        bigint telegram_id FK
        string role
        text summary "LLM-generated description"
        jsonb structured_data "skills, rates, etc"
        vector embedding "pgvector 1536d"
        bool is_complete
        timestamp created_at
    }
    
    matches {
        uuid id PK
        uuid profile_a FK
        uuid profile_b FK
        float similarity_score
        text match_rationale "LLM explanation"
        string status "pending|a_accepted|b_accepted|connected|rejected"
        timestamp created_at
    }
```

## Key Implementation Details

### 1. LLM Abstraction Layer

A simple protocol-based abstraction to swap providers:

```python
from typing import Protocol

class LLMProvider(Protocol):
    async def chat(self, messages: list[dict], system: str) -> str: ...
    async def embed(self, text: str) -> list[float]: ...
```

- OpenAI: `gpt-4o-mini` for chat, `text-embedding-3-small` for vectors
- Anthropic: `claude-3-5-sonnet` for chat, use OpenAI for embeddings (Anthropic has none)
- Config-driven provider selection via environment variables

### 2. Conversation Flow

The bot uses a system prompt that instructs the LLM to:

1. Determine user role (seeker vs provider) early
2. Ask relevant questions based on role
3. Extract structured info while maintaining natural conversation
4. Signal when profile is "complete enough" via a special token/JSON

State machine states:

- `onboarding` - initial role selection
- `profiling` - gathering information
- `active` - profile complete, eligible for matching
- `paused` - user opted out temporarily

### 3. Profile Generation

Once the LLM signals completion:

1. Generate a structured summary from conversation history
2. Extract structured fields (skills, experience, budget/rates, location, etc.)
3. Generate embedding vector from the summary
4. Store in `profiles` table with pgvector

### 4. Matching Engine (Cron Job)

Runs periodically (every N minutes):

1. Find all `active` profiles that haven't been matched recently
2. For each seeker, find top-K similar providers via cosine similarity:
   ```sql
   SELECT p2.*, 1 - (p1.embedding <=> p2.embedding) as similarity
   FROM profiles p1, profiles p2
   WHERE p1.role = 'seeker' AND p2.role = 'provider'
   AND similarity > 0.7
   ORDER BY similarity DESC LIMIT 5;
   ```

3. Filter out already-matched pairs
4. Create `match` records with status `pending`
5. Send notifications to both parties with match rationale

### 5. Match Consent Flow

When notified of a match:

- User sees: "Found a potential match! [View Details]"
- Details show the *other* profile summary (not contact info)
- Buttons: "Yes, connect me" / "Not interested"
- When both accept → status becomes `connected`, share contact details
- If either rejects → status becomes `rejected`

## Tech Stack Summary

| Component | Choice |

|-----------|--------|

| Framework | FastAPI + Uvicorn |

| Telegram | aiogram v3 (async-native) |

| Database | Neon PostgreSQL + pgvector |

| ORM | SQLAlchemy 2.0 (async) |

| Migrations | Alembic |

| LLM | OpenAI / Anthropic (configurable) |

| Embeddings | OpenAI text-embedding-3-small |

| Config | pydantic-settings |

| Jobs | APScheduler (in-process) or external cron |

| Packaging | uv (fast, modern) |

## Implementation Order

The work is structured in phases, each delivering a working increment:

**Phase 1: Foundation** - Project setup, database models, basic bot responding

**Phase 2: Conversation Engine** - LLM integration, conversation state, profile extraction

**Phase 3: Matching** - Embeddings, similarity search, match creation

**Phase 4: Connection Flow** - Notifications, consent handling, contact sharing

**Phase 5: Polish** - Error handling, rate limiting, monitoring, deployment config