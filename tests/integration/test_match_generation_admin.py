"""Test that MatchGeneration.execute() mirrors qualification results to the admin thread."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mitko.agents.models import MatchQualification, MatchQualificationDecision
from mitko.models.chat import Chat
from mitko.models.generation import Generation
from mitko.models.match import Match
from mitko.models.user import User
from mitko.services.match_generation import MatchGeneration

# --- Helpers ---


async def _create_user(
    session: AsyncSession,
    telegram_id: int,
    *,
    is_seeker: bool = False,
    is_provider: bool = False,
) -> User:
    user = User(
        telegram_id=telegram_id,
        is_seeker=is_seeker,
        is_provider=is_provider,
        state="active",
        embedding=[0.1] * 1536,
        matching_summary="Python dev, 5 years",
        practical_context="Remote only",
    )
    session.add(user)
    await session.flush()
    return user


async def _create_chat(session: AsyncSession, telegram_id: int) -> Chat:
    chat = Chat(telegram_id=telegram_id, message_history=[])
    session.add(chat)
    await session.flush()
    return chat


async def _create_match(
    session: AsyncSession, user_a_id: int, user_b_id: int
) -> Match:
    match = Match(
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        similarity_score=0.88,
        match_rationale="",
        status="pending",
        matching_round=1,
    )
    session.add(match)
    await session.flush()
    return match


async def _create_generation(session: AsyncSession, match: Match) -> Generation:
    generation = Generation(
        match_id=match.id,
        scheduled_for=datetime.now(),
        status="started",
    )
    session.add(generation)
    await session.flush()
    return generation


def _mock_qualifier_result(
    decision: MatchQualificationDecision, explanation: str
) -> AsyncMock:
    qualification = MatchQualification(
        decision=decision, explanation=explanation
    )  # type: ignore[arg-type]
    result = MagicMock()
    result.output = qualification
    result.usage.return_value = MagicMock(
        cache_read_tokens=0, input_tokens=10, output_tokens=5
    )
    return AsyncMock(return_value=result)


# --- Tests ---


@pytest.mark.parametrize(
    "decision,expected_prefix",
    [
        ("qualified", "✅"),
        ("disqualified", "❌"),
    ],
)
async def test_qualification_mirrored_to_admin_thread(
    db_session: AsyncSession,
    decision: MatchQualificationDecision,
    expected_prefix: str,
):
    user_a = await _create_user(db_session, 1001, is_seeker=True)
    user_b = await _create_user(db_session, 2002, is_provider=True)
    chat_a = await _create_chat(db_session, 1001)
    match = await _create_match(
        db_session, user_a.telegram_id, user_b.telegram_id
    )
    generation = await _create_generation(db_session, match)

    explanation = "Strong Python alignment, same timezone"

    with (
        patch(
            "mitko.services.match_generation.QUALIFIER_AGENT.run",
            _mock_qualifier_result(decision, explanation),
        ),
        patch(
            "mitko.services.match_generation.mirror_to_admin_thread",
            new_callable=AsyncMock,
        ) as mock_mirror,
        patch("mitko.jobs.matching_scheduler.start_matching_loop"),
        patch.object(MatchGeneration, "record_usage_and_cost"),
        patch(
            "mitko.services.match_generation.SETTINGS",
            use_hardcoded_match_intros=True,
        ),
        patch(
            "mitko.services.match_generation.send_to_user",
            new_callable=AsyncMock,
        ),
    ):
        mock_bot = MagicMock()
        service = MatchGeneration(
            bot=mock_bot, session=db_session, generation=generation, match=match
        )
        await service.execute()

    mock_mirror.assert_awaited_once()
    posted_text: str = mock_mirror.call_args[0][2]
    assert posted_text.startswith(expected_prefix)
    assert explanation in posted_text
    assert chat_a.id is not None  # chat was loaded correctly


async def test_qualification_always_calls_mirror_even_when_no_chat(
    db_session: AsyncSession,
):
    """Admin mirror is always called; mirror_to_admin_thread handles missing chat silently."""
    user_a = await _create_user(db_session, 3001, is_seeker=True)
    user_b = await _create_user(db_session, 4002, is_provider=True)
    # Intentionally no chat created for user_a
    match = await _create_match(
        db_session, user_a.telegram_id, user_b.telegram_id
    )
    generation = await _create_generation(db_session, match)

    with (
        patch(
            "mitko.services.match_generation.QUALIFIER_AGENT.run",
            _mock_qualifier_result("qualified", "Great match"),
        ),
        patch(
            "mitko.services.match_generation.mirror_to_admin_thread",
            new_callable=AsyncMock,
        ) as mock_mirror,
        patch("mitko.jobs.matching_scheduler.start_matching_loop"),
        patch.object(MatchGeneration, "record_usage_and_cost"),
        patch(
            "mitko.services.match_generation.SETTINGS",
            use_hardcoded_match_intros=True,
        ),
        patch(
            "mitko.services.match_generation.send_to_user",
            new_callable=AsyncMock,
        ),
    ):
        mock_bot = MagicMock()
        service = MatchGeneration(
            bot=mock_bot, session=db_session, generation=generation, match=match
        )
        await service.execute()

    mock_mirror.assert_awaited_once()
    assert mock_mirror.call_args[0][1] == user_a.telegram_id
