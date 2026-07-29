from datetime import date
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.item import ClothingItem
from app.models.learning import ItemPairScore, UserLearningProfile
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus, UserFeedback
from app.models.user import User
from app.services.learning_service import LearningService


def _make_outfit_with_feedback(user_id, items_data, accepted=True, rating=4, occasion="casual"):
    outfit = Outfit(
        id=uuid4(),
        user_id=user_id,
        occasion=occasion,
        status=OutfitStatus.accepted if accepted else OutfitStatus.rejected,
        weather_data={"temperature": 20, "condition": "clear"},
    )

    outfit_items = []
    for item_kwargs in items_data:
        item = ClothingItem(
            id=uuid4(),
            user_id=user_id,
            type=item_kwargs.get("type", "shirt"),
            image_path="test.jpg",
            primary_color=item_kwargs.get("primary_color", "blue"),
            style=item_kwargs.get("style", []),
        )
        oi = OutfitItem(outfit_id=outfit.id, item_id=item.id, position=0)
        oi.item = item
        outfit_items.append(oi)

    outfit.items = outfit_items

    feedback = UserFeedback(
        id=uuid4(),
        outfit_id=outfit.id,
        accepted=accepted,
        rating=rating,
    )
    outfit.feedback = feedback

    return outfit


@pytest_asyncio.fixture
async def test_user_for_learning(db_session):
    uid = uuid4()
    user = User(
        id=uid,
        external_id=f"test-{uid}",
        email=f"test-{uid}@example.com",
        display_name="Test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


class TestIncrementalEMA:
    @pytest.mark.asyncio
    async def test_ema_computation(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        service = LearningService(db_session)

        profile = UserLearningProfile(
            user_id=user_id,
            learned_color_scores={"blue": 0.5},
            learned_style_scores={"casual": 0.3},
            learned_occasion_patterns={},
            feedback_count=5,
        )
        db_session.add(profile)
        await db_session.flush()

        outfit = _make_outfit_with_feedback(
            user_id,
            [{"primary_color": "blue", "style": ["casual"]}],
            accepted=True,
            rating=5,
        )

        signal = service._get_outfit_signal(outfit)
        assert signal > 0

        await service._update_profile_incremental(user_id, outfit, signal)

        await db_session.refresh(profile)
        assert profile.learned_color_scores["blue"] != 0.5
        assert profile.feedback_count == 6

    @pytest.mark.asyncio
    async def test_creates_profile_if_missing(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        service = LearningService(db_session)

        outfit = _make_outfit_with_feedback(
            user_id,
            [{"primary_color": "red"}],
            accepted=True,
            rating=4,
        )
        signal = service._get_outfit_signal(outfit)
        await service._update_profile_incremental(user_id, outfit, signal)

        result = await db_session.execute(
            select(UserLearningProfile).where(UserLearningProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        assert profile is not None
        assert "red" in profile.learned_color_scores
        assert profile.feedback_count == 1

    @pytest.mark.asyncio
    async def test_jsonb_flag_modified(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        service = LearningService(db_session)

        profile = UserLearningProfile(
            user_id=user_id,
            learned_color_scores={"green": 0.2},
            learned_style_scores={},
            learned_occasion_patterns={},
            feedback_count=1,
        )
        db_session.add(profile)
        await db_session.flush()

        outfit = _make_outfit_with_feedback(
            user_id,
            [{"primary_color": "green", "style": ["sporty"]}],
            accepted=True,
            rating=5,
        )
        signal = service._get_outfit_signal(outfit)
        await service._update_profile_incremental(user_id, outfit, signal)

        await db_session.refresh(profile)
        assert profile.learned_color_scores["green"] != 0.2
        assert "sporty" in profile.learned_style_scores

    @pytest.mark.asyncio
    async def test_process_feedback_uses_incremental(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        service = LearningService(db_session)

        item = ClothingItem(
            id=uuid4(),
            user_id=user_id,
            type="shirt",
            image_path="test.jpg",
            primary_color="navy",
            style=["classic"],
        )
        db_session.add(item)

        outfit = Outfit(
            id=uuid4(),
            user_id=user_id,
            occasion="work",
            scheduled_for=date(2026, 3, 8),
            status=OutfitStatus.accepted,
            source=OutfitSource.on_demand,
        )
        db_session.add(outfit)
        await db_session.flush()

        oi = OutfitItem(outfit_id=outfit.id, item_id=item.id, position=0)
        db_session.add(oi)

        feedback = UserFeedback(
            outfit_id=outfit.id,
            accepted=True,
            rating=4,
        )
        db_session.add(feedback)
        await db_session.commit()

        with patch.object(service, "recompute_learning_profile") as mock_recompute:
            await service.process_feedback(outfit.id, user_id)
            mock_recompute.assert_not_called()

        result = await db_session.execute(
            select(UserLearningProfile).where(UserLearningProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        assert profile is not None
        assert profile.feedback_count >= 1


class TestItemPairScores:
    async def _seed_two_item_outfit(self, db_session, user_id, *, accepted, rating):
        items = []
        for color in ("blue", "black"):
            item = ClothingItem(
                id=uuid4(),
                user_id=user_id,
                type="shirt",
                image_path="test.jpg",
                primary_color=color,
                style=["casual"],
            )
            db_session.add(item)
            items.append(item)

        outfit = Outfit(
            id=uuid4(),
            user_id=user_id,
            occasion="casual",
            status=OutfitStatus.accepted if accepted else OutfitStatus.rejected,
            source=OutfitSource.on_demand,
            weather_data={"temperature": 20, "condition": "clear"},
        )
        db_session.add(outfit)
        await db_session.flush()

        for pos, item in enumerate(items):
            db_session.add(OutfitItem(outfit_id=outfit.id, item_id=item.id, position=pos))
        db_session.add(UserFeedback(outfit_id=outfit.id, accepted=accepted, rating=rating))
        await db_session.commit()
        return outfit.id

    @pytest.mark.asyncio
    async def test_accept_without_rating_creates_pair_and_context(
        self, db_session, test_user_for_learning
    ):
        user_id = test_user_for_learning.id
        outfit_id = await self._seed_two_item_outfit(
            db_session, user_id, accepted=True, rating=None
        )

        await LearningService(db_session).process_feedback(outfit_id, user_id)

        rows = (
            (
                await db_session.execute(
                    select(ItemPairScore).where(ItemPairScore.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        pair = rows[0]
        assert pair.times_paired == 1
        assert pair.times_accepted == 1
        assert "casual" in (pair.occasion_performance or {})
        assert pair.occasion_performance["casual"]["count"] == 1
