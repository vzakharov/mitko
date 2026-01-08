"""English locale implementation"""

from dataclasses import dataclass
from textwrap import dedent

from .base import (
    AgentExamples,
    AgentExamplesConversation,
    AgentExamplesRationale,
    Commands,
    CommandsReset,
    CommandsStart,
    Keyboards,
    KeyboardsMatch,
    KeyboardsReset,
    Locale,
    Matching,
    MatchingErrors,
    Profile,
    System,
    SystemErrors,
)


# Concrete English implementation
@dataclass
class EnglishLocale(Locale):
    language = "en"
    commands = Commands(
        start=CommandsStart(
            GREETING=dedent(
                """\
                Oh hey! I'm Mitko 👋

                Basically I'm like a matchmaker, except I match tech folks with jobs (and vice
                versa). We'll chat a bit so I understand what you're after, then I'll find you
                some great matches.

                So, what's up: looking for work or hiring someone?"""
            )
        ),
        reset=CommandsReset(
            NO_PROFILE="You don't have a profile yet. Hit /start and let's get you set up!",
            WARNING=dedent(
                """\
                ⚠️ Sure you wanna wipe everything?

                If you hit "Yes", I'll delete:
                • All your profile info
                • Our conversation history
                • And we'll start from scratch

                Your current matches will stay though.

                For real?"""
            ),
            SUCCESS=dedent(
                """\
                ✅ Done, wiped it all! Now I've got amnesia about you 😄

                By the way, hey, I'm Mitko!"""
            ),
            CANCELLED="Alright, leaving your profile as is.",
        ),
    )
    keyboards = Keyboards(
        match=KeyboardsMatch(ACCEPT="Yeah, let's connect!", REJECT="Nah, pass"),
        reset=KeyboardsReset(CONFIRM="Yep, wipe it", CANCEL="Nah, keep it"),
    )
    matching = Matching(
        FOUND=dedent(
            """\
            🎯 Hey, I think I found someone!

            {profile}

            💡 Why I think it's a fit: {rationale}

            Wanna connect?"""
        ),
        ACCEPT_WAITING="Got it! Now waiting to hear from the other side.",
        ACCEPT_CONNECTED="We're on! Check your messages.",
        CONNECTION_MADE=dedent(
            """\
            🎉 Boom, matched! Here's the details:

            {profile}

            You can reach out to them directly now."""
        ),
        REJECT_NOTED="Cool, got it. I'll find someone better!",
        errors=MatchingErrors(
            NOT_FOUND="Match not found",
            UNAUTHORIZED="You don't have access to this match",
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
            MESSAGE_UNAVAILABLE="Hmm, can't access that message anymore. Try again?",
        )
    )
    agent_examples = AgentExamples(
        conversation=AgentExamplesConversation(
            ONBOARDING=[
                "Hey! I'm Mitko 👋 What's your name?",
                "Alex, awesome! Do you know what I do, or should I explain real quick?",
                "Nice, you're in the loop! Let's jump right in: looking for work or hiring?",
                (
                    "Cool, quick version: I match tech people with jobs using semantic search. "
                    "So: looking for work or hiring someone?"
                ),
                "Oh, so you're job hunting! Cool. What kind of role are you after?",
                "Got it, you're hiring! What position needs filling?",
            ],
            PROFILE_CREATED=[
                (
                    "Awesome! I've got the picture now. I'll start looking for matches "
                    "and ping you when I find someone interesting!"
                ),
                "Sweet, profile's ready! I'll let you know as soon as I find good matches.",
                (
                    "Alright, got it all down! Starting the search now. "
                    "I'll hit you up when something comes up 👌"
                ),
            ],
            PROFILE_UPDATED=[
                "Done! Changed your location to Berlin. You're all set.",
                "Updated! Tech stack's been changed. Need anything else tweaked?",
                "Noted! If you wanna change anything else — just say the word.",
            ],
        ),
        rationale=AgentExamplesRationale(
            EXAMPLES=[
                (
                    "This candidate's React experience is spot-on for what you need on the "
                    "frontend, and they're free exactly when you need them."
                ),
                (
                    "Senior Python/Django — that's exactly what you're after, "
                    "plus they're in the same timezone."
                ),
            ]
        ),
    )
    OFF_TOPIC_REDIRECT = (
        "Hey, I'm having fun talking about <...> too, but you're holding up the queue and "
        "someone else might miss out on finding work because I'm not helping them 🥺 "
        "Mind getting back on track? No hard feelings!"
    )
    JAILBREAK_RESPONSE = (
        "Buddy, you're trying too hard 😄 The code's all open source, "
        "just check {repo_url} yourself!"
    )
    UNCERTAINTY_PHRASE = (
        "Look, I could make stuff up right now, but you shouldn't trust it too much. "
        "Hallucinations and all that, you know? Better to check with the creator or docs."
    )
