"""English locale implementation"""

from textwrap import dedent

from .base import (
    Admin,
    AgentExamples,
    AgentExamplesChat,
    AgentExamplesRationale,
    Announcement,
    Commands,
    CommandsReset,
    CommandsStart,
    Keyboards,
    KeyboardsActivate,
    KeyboardsMatch,
    KeyboardsReset,
    Locale,
    Matching,
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
                Hey, I'm Mitko, your IT matchmaker 👋

                Be honest, aren't you tired of this whole thing where every time you want to find a job — or a hire — you have to go through all those job postings, CVs, cover letters? And then wait while masses of HR folks and managers at every level conduct all their interviews, so that — THANK THE GODS! — finally two people who'll be coding, designing, marketing, conquering the world side by side can actually talk?

                I'm trying to change that.

                How? I match people who'll be working directly with each other. Not recruiters and distant bosses who'll hear the candidate's name twice (at hire and departure, lol) — but actual future colleagues.

                So we'll chat a bit, I'll understand your "special something," and then I'll quietly look for people "on the other side of hiring" who I think would be the best fit for you as a future colleague.

                If you _both_ agree, I'll share contact details and you can connect directly. And from there, if everything clicks, you can loop in the HR folks and even score that referral bonus 😉

                Technical note: I can't look at images, read files, or browse the internet yet, even though I might sometimes hallucinate and say I can. But you can always copy-paste text into the chat.

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
        activate=KeyboardsActivate(
            ACTIVATE="Start matching 🚀",
            ACTIVATED="You're live! I'll start looking for matches.",
        ),
    )
    matching = Matching(
        FOUND=dedent(
            """\
            🎯 Hey, I think I found someone!

            {profile}

            💡 Why I think it's a fit: {rationale}

            Wanna connect? (I'll pause matching until you respond)"""
        ),
        ACCEPT_WAITING="Got it! I'm back to looking while we wait for the other side.",
        CONNECTION_MADE="🎉 Boom, matched! Reach out: {contact}",
        REJECT_NOTED="Cool, got it. I'll find someone better!",
    )
    profile = Profile(
        CARD_HEADER="📋 Your Profile:",
        ROLE_LABEL="Role",
        ROLE_SEEKER="Job Seeker",
        ROLE_PROVIDER="Hiring/Providing",
        ROLE_SEPARATOR=" & ",
    )
    system = System(
        SCHEDULED_REPLY_SOON="Mitko will start replying very soon",
        SCHEDULED_REPLY_SHORTLY="Mitko will start replying in a minute",
        SCHEDULED_REPLY_IN="⏱️ Mitko will start replying in around {duration}",
        THINKING="💭",
        TIME_UNIT_HOUR="h",
        TIME_UNIT_MINUTE="min",
        errors=SystemErrors(
            MESSAGE_EMPTY="I see no message. Try again?",
            GENERATION_FAILED="Oops, something went wrong on my end. Please try again!",
            SOMETHING_WENT_WRONG="Oops, something went wrong. Chances are, we're on it (no promises though).",
        ),
    )
    agent_examples = AgentExamples(
        chat=AgentExamplesChat(
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
    admin = Admin(
        CHAT_INTRO="This is the beginning of a chat with {user_ref}",
        announcement=Announcement(
            PREVIEW="About to send to {count} user(s), including: {users_preview}\n\n{text}",
            YES="Yes, send",
            CANCEL="Cancel",
            SENDING="Sending...",
            DONE="Sent to {sent}/{total} users.",
            CANCELLED="Cancelled.",
            PARSE_ERROR="Could not parse filter: {error}",
            UNKNOWN_FIELD="Unknown filter field: {field}",
        ),
    )
    PROFILE_ACTIVATION_PROMPT = (
        "Click the button below if you want your profile to become available for matching, "
        "or feel free to request any edits first."
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
