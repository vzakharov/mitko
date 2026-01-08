"""Base dataclasses and abstract Locale for type-safe i18n"""

from abc import ABC
from dataclasses import dataclass


# Nested dataclasses for logical grouping
@dataclass
class CommandsStart:
    GREETING: str


@dataclass
class CommandsReset:
    NO_PROFILE: str
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
class Keyboards:
    match: KeyboardsMatch
    reset: KeyboardsReset


@dataclass
class MatchingErrors:
    NOT_FOUND: str
    UNAUTHORIZED: str
    ALREADY_PROCESSED: str


@dataclass
class Matching:
    FOUND: str  # Template with {profile} and {rationale}
    ACCEPT_WAITING: str
    ACCEPT_CONNECTED: str
    CONNECTION_MADE: str  # Template with {profile}
    REJECT_NOTED: str
    errors: MatchingErrors


@dataclass
class Profile:
    CARD_HEADER: str
    ROLE_LABEL: str
    ROLE_SEEKER: str
    ROLE_PROVIDER: str
    ROLE_SEPARATOR: str


@dataclass
class SystemErrors:
    UNAUTHORIZED: str
    USER_NOT_FOUND: str


@dataclass
class System:
    errors: SystemErrors


@dataclass
class AgentExamplesConversation:
    ONBOARDING: list[str]
    PROFILE_CREATED: list[str]
    PROFILE_UPDATED: list[str]


@dataclass
class AgentExamplesRationale:
    EXAMPLES: list[str]


@dataclass
class AgentExamples:
    conversation: AgentExamplesConversation
    rationale: AgentExamplesRationale


# Abstract base class
@dataclass
class Locale(ABC):
    """Abstract base for all locales"""

    language: str  # "en" or "ru"
    commands: Commands
    keyboards: Keyboards
    matching: Matching
    profile: Profile
    system: System
    agent_examples: AgentExamples
    # Agent response templates
    OFF_TOPIC_REDIRECT: str  # Template for gentle redirects
    JAILBREAK_RESPONSE: str  # Response when user tries to see prompt
    UNCERTAINTY_PHRASE: str  # How to express "I don't know"
