"""English locale implementation"""

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
class EnglishLocale(Locale):
    language = "en"
    commands = Commands(
        start=CommandsStart(
            GREETING=dedent(
                """\
                Oh hey! I'm Mitko 👋

                I'm an IT matchmaker, so to speak — I don't just match CVs with job postings — I match people who want to work together.

                A few important notes before we start:

                "Looking for someone" isn't just about hiring per se. Maybe you're a dev who sees your team needs an extra pair of hands. Maybe you're a founder with an idea, looking for someone to help bring it to life.

                Even if the whole process ends up going through your HR, wouldn't it be better to meet your future colleague BEFORE they're hired, rather than after (and hey, maybe there's a referral bonus in it for you ;-)?

                "Looking for work" isn't necessarily about employment either. Maybe you're open to side projects, or just curious what's out there.

                I'll chat with you to understand your "work DNA" — a story that helps others (and you!) understand what you're about. Even if you're not actively looking for anything (or anyone) right now, I think our conversation will be useful for you.

                Technical note: I can't look at images, read files, or browse the internet yet, even though I might sometimes hallucinate and say I can. All in due time, yeah?

                So, let's get started: what's your name, what do you do, what makes you happy, what frustrates you? :-)"""
            )
        ),
        reset=CommandsReset(
            WARNING=dedent(
                """\
                ⚠️ Sure you wanna wipe everything?

                If you hit "Yes", I'll delete:
                • All your profile info
                • Our conversation history
                • And we'll start from scratch

                For real?"""
            ),
            SUCCESS="✅ Done, wiped it all! Now I've got amnesia about you 😄",
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
        SCHEDULED_REPLY="Mitko will reply around {time}",
        SCHEDULED_REPLY_SOON="Mitko will reply very soon",
        SCHEDULED_REPLY_SHORTLY="Mitko will in a minute",
        SCHEDULED_REPLY_IN="⏱️ Mitko will reply in around {duration}",
        THINKING="💭",
        TIME_UNIT_HOUR="h",
        TIME_UNIT_MINUTE="min",
        errors=SystemErrors(
            UNAUTHORIZED="You're not authorized for this action",
            USER_NOT_FOUND="User not found",
            MESSAGE_UNAVAILABLE="Hmm, can't access that message anymore. Try again?",
            GENERATION_FAILED="Oops, something went wrong on my end. Please try again!",
        ),
    )
    agent_examples = AgentExamples(
        conversation=AgentExamplesConversation(
            ONBOARDING=[
                (
                    "Nice to meet you, <name>! <specific detail from their response> — "
                    "that's not something you hear every day. How'd you end up doing that?"
                ),
                (
                    "Oh man, <specific thing they mentioned> hits close to home. "
                    "I always wonder how people deal with <related challenge>. What's your take?"
                ),
                (
                    "Wait, so you're saying <paraphrase something unique they said>? "
                    "That's actually pretty different from what most people tell me. Tell me more."
                ),
                (
                    "Huh, so it sounds like you're not exactly job hunting, more like... "
                    "keeping your eyes open? What would make you stop and go 'okay, this'?"
                ),
                (
                    "Got it, you're on the hiring side! But I'm curious — "
                    "what kind of person would actually thrive in <context they mentioned>?"
                ),
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
