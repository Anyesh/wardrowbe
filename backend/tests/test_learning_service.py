from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus
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


async def _seed_outfit(db_session, user_id, colors, *, occasion="work", day=1, accepted=True):
    outfit = Outfit(
        id=uuid4(),
        user_id=user_id,
        occasion=occasion,
        scheduled_for=date(2026, 3, day),
        status=OutfitStatus.accepted if accepted else OutfitStatus.rejected,
        source=OutfitSource.on_demand,
    )
    db_session.add(outfit)
    for position, color in enumerate(colors):
        item = ClothingItem(
            id=uuid4(), user_id=user_id, type="shirt", image_path="t.jpg", primary_color=color
        )
        db_session.add(item)
        await db_session.flush()
        db_session.add(OutfitItem(outfit_id=outfit.id, item_id=item.id, position=position))
    db_session.add(UserFeedback(outfit_id=outfit.id, accepted=accepted, rating=5))
    await db_session.commit()


class TestAcceptanceRateOfZero:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("accepted", "learning_rate", "analytics_rate"),
        [
            pytest.param(True, 1.0, 100.0, id="all-accepted"),
            pytest.param(False, 0.0, 0.0, id="all-rejected"),
        ],
    )
    async def test_is_reported_as_zero_not_missing(
        self, client, db_session, test_user, auth_headers, accepted, learning_rate, analytics_rate
    ):
        for day in (1, 2, 3):
            await _seed_outfit(db_session, test_user.id, ["navy"], day=day, accepted=accepted)

        learning = await client.post("/api/v1/learning/recompute", headers=auth_headers)
        analytics = await client.get("/api/v1/analytics", headers=auth_headers)

        assert learning.json()["overall_acceptance_rate"] == pytest.approx(learning_rate)
        assert analytics.json()["wardrobe"]["acceptance_rate"] == pytest.approx(analytics_rate)


class TestLearnedColoursAreCanonical:
    @pytest.mark.asyncio
    async def test_recompute_stores_canonical_colours(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        await _seed_outfit(db_session, user_id, ["charcoal", "Khaki"], day=1)
        await _seed_outfit(db_session, user_id, ["gray"], day=2)

        profile = await LearningService(db_session).recompute_learning_profile(user_id)

        assert set(profile.learned_color_scores) == {"gray", "tan"}
        assert profile.learned_occasion_patterns["work"]["preferred_colors"] == ["gray", "tan"]

    @pytest.mark.asyncio
    async def test_incremental_update_merges_aliased_colours(
        self, db_session, test_user_for_learning
    ):
        user_id = test_user_for_learning.id
        db_session.add(
            UserLearningProfile(
                user_id=user_id,
                learned_color_scores={
                    "charcoal": 0.6,
                    "gray": 0.2,
                    "teal": -0.4,
                    "olive": "high",
                    "tan": None,
                    "cream": True,
                    "\u00a0": 0.9,
                    "navy": 10**400,
                    "plum": -(10**400),
                },
                learned_style_scores={"boho": "high", "minimal": 0.3, "preppy": 10**399},
                learned_occasion_patterns={
                    "casual": {"preferred_colors": ["charcoal", "gray"]},
                    "wedding": "often",
                },
                feedback_count=3,
            )
        )
        await db_session.flush()
        outfit = _make_outfit_with_feedback(user_id, [{"primary_color": "Charcoal"}], rating=5)
        service = LearningService(db_session)
        signal = service._get_outfit_signal(outfit)

        await service._update_profile_incremental(user_id, outfit, signal)

        profile = await db_session.get(UserLearningProfile, user_id)
        await db_session.refresh(profile)
        assert set(profile.learned_color_scores) == {"gray", "blue"}
        alpha = service.EMA_ALPHA
        assert profile.learned_color_scores["gray"] == round(0.4 * (1 - alpha) + signal * alpha, 3)
        assert profile.learned_color_scores["blue"] == -0.4
        assert profile.learned_occasion_patterns["casual"]["preferred_colors"] == ["gray"]
        assert profile.learned_style_scores == {"minimal": 0.3}
        assert "wedding" not in profile.learned_occasion_patterns


READABLE_PROFILE = {
    "learned_color_scores": {"black": 0.9},
    "learned_style_scores": {"minimal": 0.8},
    "learned_occasion_patterns": {"formal": {"preferred_colors": ["black"], "success_rate": 0.8}},
    "learned_weather_preferences": {"mild": {"preferred_layers": 2.0, "success_rate": 0.5}},
}
JUNK_ENTRIES = [
    pytest.param("learned_color_scores", "navy", "high", id="colour-string"),
    pytest.param("learned_color_scores", "navy", [0.5], id="colour-list"),
    pytest.param("learned_color_scores", "navy", {"score": 0.5}, id="colour-dict"),
    pytest.param("learned_color_scores", "navy", True, id="colour-bool"),
    pytest.param("learned_color_scores", "navy", None, id="colour-null"),
    pytest.param("learned_color_scores", "navy", 10**400, id="colour-1e400-from-jsonb"),
    pytest.param("learned_color_scores", "navy", 10**399, id="colour-400-digits"),
    pytest.param("learned_color_scores", "navy", -(10**400), id="colour-minus-1e400"),
    pytest.param("learned_style_scores", "boho", "high", id="style-string"),
    pytest.param("learned_style_scores", "boho", True, id="style-bool"),
    pytest.param("learned_style_scores", "boho", 10**400, id="style-1e400-from-jsonb"),
    pytest.param("learned_occasion_patterns", "wedding", "often", id="occasion-string"),
    pytest.param(
        "learned_occasion_patterns", "wedding", {"preferred_colors": "navy"}, id="occasion-colours"
    ),
    pytest.param(
        "learned_occasion_patterns", "wedding", {"preferred_colors": [1]}, id="occasion-colour-int"
    ),
    pytest.param(
        "learned_occasion_patterns", "wedding", {"success_rate": "high"}, id="occasion-rate"
    ),
    pytest.param("learned_weather_preferences", "freezing", [], id="weather-list"),
    pytest.param(
        "learned_weather_preferences", "freezing", {"preferred_layers": "many"}, id="weather-layers"
    ),
]


def _learned_prompt_lines(prompt: str) -> str:
    return "\n".join(
        line for line in prompt.splitlines() if line.startswith(("- Learned", "- For ", "- Low"))
    )


class TestJunkLearnedProfileIsIgnored:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/api/v1/learning"),
            ("post", "/api/v1/learning/recompute"),
            ("post", "/api/v1/learning/generate-insights"),
            ("post", "/api/v1/outfits/suggest"),
        ],
    )
    @pytest.mark.parametrize(("field", "junk_key", "junk_value"), JUNK_ENTRIES)
    async def test_readers_skip_junk_entries(
        self, client, db_session, test_user, auth_headers, method, path, field, junk_key, junk_value
    ):
        profile = {name: dict(entries) for name, entries in READABLE_PROFILE.items()}
        profile[field][junk_key] = junk_value
        db_session.add(
            UserLearningProfile(
                user_id=test_user.id,
                **profile,
                feedback_count=3,
                last_computed_at=datetime.now(UTC),
            )
        )
        for item_type in ("shirt", "pants"):
            db_session.add(
                ClothingItem(
                    user_id=test_user.id,
                    type=item_type,
                    image_path=f"test/{uuid4()}.jpg",
                    status=ItemStatus.ready,
                    primary_color="black",
                )
            )
        await db_session.commit()
        ai_reply = SimpleNamespace(
            content='{"items": [1, 2], "headline": "x"}', model="m", endpoint="e"
        )

        with patch(
            "app.services.recommendation_service.AIService.generate_text",
            new_callable=AsyncMock,
            return_value=ai_reply,
        ) as generate_text:
            response = await client.request(
                method,
                path,
                json={
                    "occasion": "wedding",
                    "weather_override": {"temperature": 20, "condition": "clear"},
                },
                headers=auth_headers,
            )

        assert response.status_code == 200, response.text
        seen = (
            _learned_prompt_lines(generate_text.call_args.args[0])
            if generate_text.called
            else response.text
        )
        assert "black" in seen
        assert junk_key not in seen
