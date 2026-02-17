"""Base dataclasses and abstract Locale for type-safe i18n"""

from abc import ABC
from dataclasses import dataclass


# Nested dataclasses for logical grouping
@dataclass
class CommandsStart:
    GREETING: str


@dataclass
class CommandsReset:
    WARNING: str
    SUCCESS: str
    CANCELLED: str


@dataclass
class Commands:
    start: CommandsStart
    reset: CommandsReset


@dataclass
class KeyboardsMatch:
    ACCEPT: str
    REJECT: str


@dataclass
class KeyboardsReset:
    CONFIRM: str
    CANCEL: str


@dataclass
class KeyboardsActivate:
    ACTIVATE: str
    ACTIVATED: str


@dataclass
class Keyboards:
    match: KeyboardsMatch
    reset: KeyboardsReset
    activate: KeyboardsActivate


@dataclass
class Matching:
    FOUND: str  # Template with {profile} and {rationale}
    ACCEPT_WAITING: str
    CONNECTION_MADE: str  # Template with {profile}
    REJECT_NOTED: str


@dataclass
class Profile:
    CARD_HEADER: str
    ROLE_LABEL: str
    ROLE_SEEKER: str
    ROLE_PROVIDER: str
    ROLE_SEPARATOR: str


@dataclass
class SystemErrors:
    MESSAGE_EMPTY: str
    GENERATION_FAILED: str
    SOMETHING_WENT_WRONG: str


@dataclass
class System:
    SCHEDULED_REPLY_SOON: str  # "will reply very soon"
    SCHEDULED_REPLY_SHORTLY: str  # "will reply shortly"
    SCHEDULED_REPLY_IN: (
        str  # Template with {duration} - "will reply in around {duration}"
    )
    THINKING: str  # Thinking emoji (💭)
    TIME_UNIT_HOUR: str  # "h" (EN) / "ч" (RU)
    TIME_UNIT_MINUTE: str  # "min" (EN) / "мин" (RU)
    errors: SystemErrors


@dataclass
class AgentExamplesChat:
    ONBOARDING: list[str]
    PROFILE_CREATED: list[str]
    PROFILE_UPDATED: list[str]


@dataclass
class AgentExamplesRationale:
    EXAMPLES: list[str]


@dataclass
class AgentExamples:
    chat: AgentExamplesChat
    rationale: AgentExamplesRationale


@dataclass
class Announcement:
    PREVIEW: str  # Template: {count}, {users_preview}, {text}
    YES: str
    CANCEL: str
    SENDING: str
    DONE: str  # Template: {sent}, {total}
    CANCELLED: str
    PARSE_ERROR: str  # Template: {error}
    UNKNOWN_FIELD: str  # Template: {field}


@dataclass
class Admin:
    CHAT_HEADER: str  # Template with {user_id}
    CHAT_INTRO: str
    announcement: Announcement


# Abstract base class
class Locale(ABC):
    """Abstract base for all locales"""

    language: str  # "en" or "ru"
    commands: Commands
    keyboards: Keyboards
    matching: Matching
    profile: Profile
    system: System
    agent_examples: AgentExamples
    admin: Admin
    PROFILE_ACTIVATION_PROMPT: (
        str  # Appended after profile card to prompt activation
    )
    # Agent response templates
    OFF_TOPIC_REDIRECT: str  # Template for gentle redirects
    JAILBREAK_RESPONSE: str  # Response when user tries to see prompt
    UNCERTAINTY_PHRASE: str  # How to express "I don't know"
