"""English locale implementation"""

from dataclasses import dataclass

from .base import (
    Locale,
    Commands,
    CommandsStart,
    CommandsReset,
    Keyboards,
    KeyboardsMatch,
    KeyboardsReset,
    Matching,
    MatchingErrors,
    Profile,
    System,
    SystemErrors,
    AgentExamples,
    AgentExamplesConversation,
    AgentExamplesRationale,
)


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
