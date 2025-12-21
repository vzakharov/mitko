"""Type-safe internationalization module for Mitko bot"""

from dataclasses import dataclass
from abc import ABC
from functools import lru_cache

from .config import settings


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


# Concrete English implementation
@dataclass
class EnglishLocale(Locale):
    language = "en"
    commands = Commands(
        start=CommandsStart(
            GREETING="Hi! I'm Mitko, your IT matchmaking assistant. I'll chat with you to understand what you're looking for, then help connect you with great matches.\n\nAre you looking for work, or are you hiring?"
        ),
        reset=CommandsReset(
            NO_PROFILE="You don't have an active profile yet. Use /start to begin!",
            WARNING="⚠️ Reset Your Profile\n\nThis will permanently:\n• Delete your profile information\n• Clear your conversation history\n• Return you to the onboarding process\n\nYour existing matches will be preserved.\n\nAre you sure you want to continue?",
            SUCCESS="✅ Profile Reset Complete\n\nYour profile and conversation history have been cleared.\nYou're now back at the beginning.\n\nReady to start fresh? Tell me: are you looking for work, or are you hiring?",
            CANCELLED="Reset cancelled. Your profile remains unchanged.",
        ),
    )
    keyboards = Keyboards(
        match=KeyboardsMatch(ACCEPT="Yes, connect me", REJECT="Not interested"),
        reset=KeyboardsReset(CONFIRM="Yes, reset my profile", CANCEL="Cancel"),
    )
    matching = Matching(
        FOUND="🎯 Found a potential match!\n\n{profile}\n\n💡 Why this match: {rationale}\n\nWould you like to connect?",
        ACCEPT_WAITING="Thanks! Waiting for the other party to respond.",
        ACCEPT_CONNECTED="Connected! Check your messages for details.",
        CONNECTION_MADE="🎉 Connection made! Here are the details:\n\n{profile}\n\nYou can now contact them directly.",
        REJECT_NOTED="Noted. We'll find better matches for you!",
        errors=MatchingErrors(
            NOT_FOUND="Match not found",
            UNAUTHORIZED="You're not authorized for this match",
            ALREADY_PROCESSED="This match is already processed",
        ),
    )
    profile = Profile(
        CARD_HEADER="📋 Your Profile:",
        ROLE_LABEL="Role",
        ROLE_SEEKER="Job Seeker",
        ROLE_PROVIDER="Hiring/Providing",
        ROLE_SEPARATOR=" & ",
    )
    system = System(
        errors=SystemErrors(
            UNAUTHORIZED="You're not authorized for this action",
            USER_NOT_FOUND="User not found",
        )
    )
    agent_examples = AgentExamples(
        conversation=AgentExamplesConversation(
            ONBOARDING=[
                "Great to meet you! So you're looking for work - what kind of role are you interested in?",
                "I see you're hiring! What position are you looking to fill?",
                "Got it! You're both looking for work and hiring others. Let's start with what you're looking for - what kind of role interests you?",
            ],
            PROFILE_CREATED=[
                "Perfect! I've got a good picture of what you're looking for. I'll start searching for matches and let you know when I find someone interesting!",
                "Excellent! Your profile is all set. I'll notify you when I find good matches.",
            ],
            PROFILE_UPDATED=[
                "Done! I've updated your location to Berlin. Your profile is now up to date.",
                "Updated! I've changed your tech stack. Let me know if there's anything else you'd like to adjust.",
            ],
        ),
        rationale=AgentExamplesRationale(
            EXAMPLES=[
                "This candidate's React expertise aligns perfectly with your frontend needs, and their availability matches your timeline.",
                "Their senior-level experience in Python/Django is exactly what you're looking for, and they're based in the same timezone.",
            ]
        ),
    )


# Concrete Russian implementation
@dataclass
class RussianLocale(Locale):
    language = "ru"
    commands = Commands(
        start=CommandsStart(
            GREETING="Привет! Я Митко, ваш IT-ассистент по подбору. Я пообщаюсь с вами, чтобы понять, что вы ищете, а затем помогу найти отличные совпадения.\n\nВы ищете работу или нанимаете?"
        ),
        reset=CommandsReset(
            NO_PROFILE="У вас ещё нет активного профиля. Используйте /start, чтобы начать!",
            WARNING="⚠️ Сброс профиля\n\nЭто действие безвозвратно:\n• Удалит информацию профиля\n• Очистит историю разговоров\n• Вернёт вас к началу регистрации\n\nВаши текущие совпадения будут сохранены.\n\nВы уверены, что хотите продолжить?",
            SUCCESS="✅ Профиль сброшен\n\nВаш профиль и история разговоров очищены.\nВы вернулись к началу.\n\nГотовы начать заново? Расскажите: вы ищете работу или нанимаете?",
            CANCELLED="Сброс отменён. Ваш профиль не изменён.",
        ),
    )
    keyboards = Keyboards(
        match=KeyboardsMatch(ACCEPT="Да, познакомьте", REJECT="Не интересно"),
        reset=KeyboardsReset(CONFIRM="Да, сбросить профиль", CANCEL="Отмена"),
    )
    matching = Matching(
        FOUND="🎯 Найдено потенциальное совпадение!\n\n{profile}\n\n💡 Почему это подходит: {rationale}\n\nХотите связаться?",
        ACCEPT_WAITING="Спасибо! Ждём ответа другой стороны.",
        ACCEPT_CONNECTED="Связь установлена! Проверьте сообщения для деталей.",
        CONNECTION_MADE="🎉 Связь установлена! Вот детали:\n\n{profile}\n\nТеперь вы можете связаться напрямую.",
        REJECT_NOTED="Понятно. Найдём для вас лучшие варианты!",
        errors=MatchingErrors(
            NOT_FOUND="Совпадение не найдено",
            UNAUTHORIZED="У вас нет доступа к этому совпадению",
            ALREADY_PROCESSED="Это совпадение уже обработано",
        ),
    )
    profile = Profile(
        CARD_HEADER="📋 Ваш профиль:",
        ROLE_LABEL="Роль",
        ROLE_SEEKER="Ищу работу",
        ROLE_PROVIDER="Нанимаю",
        ROLE_SEPARATOR=" и ",
    )
    system = System(
        errors=SystemErrors(
            UNAUTHORIZED="У вас нет доступа к этому действию",
            USER_NOT_FOUND="Пользователь не найден",
        )
    )
    agent_examples = AgentExamples(
        conversation=AgentExamplesConversation(
            ONBOARDING=[
                "Приятно познакомиться! Вы ищете работу - какая должность вас интересует?",
                "Понимаю, вы нанимаете! Какую позицию хотите заполнить?",
                "Ясно! Вы и ищете работу, и нанимаете. Начнём с того, что вы ищете - какая роль вас интересует?",
            ],
            PROFILE_CREATED=[
                "Отлично! Теперь мне ясно, что вы ищете. Начну искать совпадения и сообщу, когда найду кого-то интересного!",
                "Превосходно! Ваш профиль готов. Я уведомлю вас, когда найду подходящие совпадения.",
            ],
            PROFILE_UPDATED=[
                "Готово! Обновил ваше местоположение на Берлин. Профиль актуален.",
                "Обновлено! Изменил технологический стек. Дайте знать, если нужно что-то ещё поправить.",
            ],
        ),
        rationale=AgentExamplesRationale(
            EXAMPLES=[
                "Опыт этого кандидата в React идеально соответствует вашим требованиям к фронтенду, и его доступность совпадает с вашими сроками.",
                "Их senior-уровень опыта в Python/Django - именно то, что вы ищете, и они находятся в том же часовом поясе.",
            ]
        ),
    )


# Singleton factory
@lru_cache(maxsize=1)
def get_locale() -> Locale:
    """Get locale instance based on MITKO_LANGUAGE env variable"""
    if settings.mitko_language == "ru":
        return RussianLocale()
    return EnglishLocale()


# Singleton instance - short name for convenience
L = get_locale()

__all__ = ["Locale", "EnglishLocale", "RussianLocale", "get_locale", "L"]
