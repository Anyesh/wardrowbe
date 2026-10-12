from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models.item import ClothingItem, ItemStatus
from app.models.learning import ItemPairScore, StyleInsight, UserLearningProfile
from app.models.outfit import Outfit, OutfitItem, OutfitSource, OutfitStatus, UserFeedback
from app.models.user import User
from app.services.learning_service import LearningService, insight_message, score_interpretation


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


async def _profile(db_session, user_id) -> UserLearningProfile:
    db_session.expire_all()
    return await db_session.scalar(
        select(UserLearningProfile).where(UserLearningProfile.user_id == user_id)
    )


class TestProcessFeedbackProfile:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status",
        [
            pytest.param(OutfitStatus.accepted, id="accepted-suggestion"),
            pytest.param(OutfitStatus.pending, id="studio-outfit"),
        ],
    )
    async def test_one_rated_outfit_fills_the_profile_without_a_recompute(
        self, db_session, test_user_for_learning, status
    ):
        user_id = test_user_for_learning.id
        outfit_id = await _seed_outfit(
            db_session, user_id, ["navy", " \u200b"], status=status, rating=4
        )

        await LearningService(db_session).process_feedback(outfit_id, user_id)

        profile = await _profile(db_session, user_id)
        assert (profile.feedback_count, profile.outfits_rated) == (1, 1)
        assert float(profile.average_overall_rating) == 4.0
        assert float(profile.overall_acceptance_rate) == 1.0
        assert list(profile.learned_color_scores) == ["navy"]
        assert profile.learned_color_scores["navy"] > 0
        assert profile.learned_occasion_patterns["work"]["preferred_colors"] == ["navy"]

    @pytest.mark.asyncio
    async def test_repeat_feedback_leaves_the_profile_unchanged(
        self, db_session, test_user_for_learning
    ):
        user_id = test_user_for_learning.id
        await _seed_outfit(db_session, user_id, ["gray"], day=1)
        outfit_id = await _seed_outfit(db_session, user_id, ["navy", "red"], day=2)
        service = LearningService(db_session)

        snapshots = []
        for _ in range(2):
            await service.process_feedback(outfit_id, user_id)
            profile = await _profile(db_session, user_id)
            snapshots.append(
                (
                    profile.learned_color_scores,
                    profile.learned_style_scores,
                    profile.learned_occasion_patterns,
                    profile.feedback_count,
                    profile.outfits_rated,
                    profile.average_overall_rating,
                    profile.overall_acceptance_rate,
                )
            )

        assert snapshots[0] == snapshots[1]
        assert snapshots[0][3] == 2

    @pytest.mark.asyncio
    async def test_negative_feedback_adds_no_preferred_colour(
        self, db_session, test_user_for_learning
    ):
        user_id = test_user_for_learning.id
        outfit_id = await _seed_outfit(db_session, user_id, ["navy"], accepted=False, rating=1)

        await LearningService(db_session).process_feedback(outfit_id, user_id)

        profile = await _profile(db_session, user_id)
        assert profile.learned_occasion_patterns["work"]["preferred_colors"] == []
        assert profile.learned_color_scores["navy"] < 0

    @pytest.mark.asyncio
    async def test_feedback_replaces_a_junk_stored_profile(
        self, db_session, test_user_for_learning
    ):
        user_id = test_user_for_learning.id
        db_session.add(
            UserLearningProfile(
                user_id=user_id,
                learned_color_scores={
                    "charcoal": 0.6,
                    "teal": -0.4,
                    "olive": "high",
                    "tan": None,
                    "\u00a0": 0.9,
                    "navy": 10**400,
                },
                learned_style_scores={"boho": "high", "preppy": 10**399},
                learned_occasion_patterns={
                    "wedding": "often",
                    "formal": {"preferred_colors": ["navy", 3], "colors": {"red": None}},
                },
                learned_weather_preferences={"hot": {"success_rate": 10**400}},
                feedback_count=3,
            )
        )
        await db_session.commit()
        outfit_id = await _seed_outfit(db_session, user_id, ["Charcoal"])

        await LearningService(db_session).process_feedback(outfit_id, user_id)

        profile = await _profile(db_session, user_id)
        assert set(profile.learned_color_scores) == {"gray"}
        assert profile.learned_style_scores == {}
        assert set(profile.learned_occasion_patterns) == {"work"}
        assert profile.learned_weather_preferences == {}
        assert profile.feedback_count == 1


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

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("first_rating", "second_rating"),
        [pytest.param(4, 4, id="same-feedback-twice"), pytest.param(2, 5, id="rating-changed")],
    )
    async def test_resubmitted_feedback_replaces_the_outfits_contribution(
        self, db_session, test_user_for_learning, first_rating, second_rating
    ):
        user_id = test_user_for_learning.id
        outfit_id = await self._seed_two_item_outfit(
            db_session, user_id, accepted=True, rating=first_rating
        )
        service = LearningService(db_session)
        await service.process_feedback(outfit_id, user_id)

        feedback = await db_session.scalar(
            select(UserFeedback).where(UserFeedback.outfit_id == outfit_id)
        )
        feedback.rating = second_rating
        await db_session.commit()
        await service.process_feedback(outfit_id, user_id)

        [pair] = await _pair_rows(db_session, user_id)
        assert (pair.times_paired, pair.times_accepted) == (1, 1)
        assert (pair.total_rating_sum, pair.rating_count) == (second_rating, 1)
        assert pair.occasion_performance == {"casual": {"count": 1, "positive": 1}}
        assert pair.weather_performance == {"mild": {"count": 1, "positive": 1}}

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("endpoint", "body"),
        [
            pytest.param("wore-instead", {"rating": 5}, id="wore-instead"),
            pytest.param("feedback", {"accepted": False, "rating": 5}, id="feedback"),
        ],
    )
    async def test_wore_instead_scores_the_replacement_pairs_once(
        self, client, db_session, test_user, auth_headers, endpoint, body
    ):
        item_ids = await _ready_items(db_session, test_user.id, ("t-shirt", "jeans", "sneakers"))
        items_field = "items" if endpoint == "wore-instead" else "wore_instead_items"
        original = Outfit(
            user_id=test_user.id,
            occasion="casual",
            scheduled_for=date(2026, 10, 1),
            status=OutfitStatus.pending,
            source=OutfitSource.on_demand,
        )
        db_session.add(original)
        await db_session.commit()

        for _ in range(2):
            response = await client.post(
                f"/api/v1/outfits/{original.id}/{endpoint}",
                json={**body, items_field: item_ids[:2]},
                headers=auth_headers,
            )
            assert response.status_code == 200

        [pair] = await _pair_rows(db_session, test_user.id)
        assert (pair.times_paired, pair.times_accepted, pair.rating_count) == (1, 1, 1)
        assert pair.total_rating_sum == 5

    @pytest.mark.asyncio
    async def test_changing_outfit_items_moves_the_counts_to_the_new_pair(
        self, client, db_session, test_user, auth_headers
    ):
        shirt, jeans, chinos = await _ready_items(
            db_session, test_user.id, ("t-shirt", "jeans", "chinos")
        )
        created = await client.post(
            "/api/v1/outfits/studio",
            json={"items": [shirt, jeans], "occasion": "casual"},
            headers=auth_headers,
        )
        assert created.status_code == 201

        patched = await client.patch(
            f"/api/v1/outfits/{created.json()['id']}",
            json={"items": [shirt, chinos]},
            headers=auth_headers,
        )

        assert patched.status_code == 200
        [pair] = await _pair_rows(db_session, test_user.id)
        assert {str(pair.item1_id), str(pair.item2_id)} == {shirt, chinos}
        assert (pair.times_paired, pair.times_accepted) == (1, 1)

    @pytest.mark.asyncio
    async def test_full_recompute_heals_drifted_pair_rows(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        outfit_id = await self._seed_two_item_outfit(db_session, user_id, accepted=True, rating=4)
        service = LearningService(db_session)
        await service.process_feedback(outfit_id, user_id)
        [pair] = await _pair_rows(db_session, user_id)
        pair.times_paired, pair.times_accepted, pair.total_rating_sum = 7, 7, 30
        [never_worn_with] = await _ready_items(db_session, user_id, ("chinos",))
        # Every writer stores item1_id < item2_id, so the stale row must too.
        stale_low, stale_high = sorted((pair.item1_id, UUID(never_worn_with)))
        db_session.add(
            ItemPairScore(
                user_id=user_id,
                item1_id=stale_low,
                item2_id=stale_high,
                times_paired=3,
            )
        )
        await db_session.commit()

        await service.recompute_learning_profile(user_id)

        [pair] = await _pair_rows(db_session, user_id)
        assert (pair.times_paired, pair.times_accepted, pair.total_rating_sum) == (1, 1, 4)

    @pytest.mark.asyncio
    async def test_full_recompute_writes_more_pairs_than_one_statement_can_bind(
        self, db_session, test_user_for_learning
    ):
        # 75 items make 2775 pairs, past the 2730 rows of 12 columns that fit in one statement's
        # 32767 bind parameters.
        user_id = test_user_for_learning.id
        await _seed_outfit(db_session, user_id, ["navy"] * 75)

        await LearningService(db_session).recompute_learning_profile(user_id)

        assert len(await _pair_rows(db_session, user_id)) == 2775


async def _pair_rows(db_session, user_id) -> list[ItemPairScore]:
    db_session.expire_all()
    return list(
        (await db_session.execute(select(ItemPairScore).where(ItemPairScore.user_id == user_id)))
        .scalars()
        .all()
    )


async def _ready_items(db_session, user_id, item_types) -> list[str]:
    items = [
        ClothingItem(
            user_id=user_id,
            type=item_type,
            image_path=f"test/{uuid4()}.jpg",
            status=ItemStatus.ready,
            primary_color="blue",
        )
        for item_type in item_types
    ]
    db_session.add_all(items)
    await db_session.commit()
    return [str(item.id) for item in items]


async def _seed_outfit(
    db_session, user_id, colors, *, occasion="work", day=1, accepted=True, status=None, rating=5
):
    outfit = Outfit(
        id=uuid4(),
        user_id=user_id,
        occasion=occasion,
        scheduled_for=date(2026, 3, day),
        status=status or (OutfitStatus.accepted if accepted else OutfitStatus.rejected),
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
    db_session.add(UserFeedback(outfit_id=outfit.id, accepted=accepted, rating=rating))
    await db_session.commit()
    return outfit.id


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
        self,
        client,
        db_session,
        test_user_with_preferences,
        auth_headers,
        accepted,
        learning_rate,
        analytics_rate,
    ):
        for day in (1, 2, 3):
            await _seed_outfit(
                db_session, test_user_with_preferences.id, ["navy"], day=day, accepted=accepted
            )

        learning = await client.post("/api/v1/learning/recompute", headers=auth_headers)
        insights = await client.get("/api/v1/learning", headers=auth_headers)
        analytics = await client.get("/api/v1/analytics", headers=auth_headers)

        assert learning.json()["overall_acceptance_rate"] == pytest.approx(learning_rate)
        assert insights.json()["profile"]["overall_acceptance_rate"] == pytest.approx(learning_rate)
        assert insights.json()["preference_suggestions"]["confidence"] == pytest.approx(
            learning_rate
        )
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


class TestOccasionColours:
    @pytest.mark.asyncio
    async def test_recompute_ranks_by_count_then_name(self, db_session, test_user_for_learning):
        user_id = test_user_for_learning.id
        await _seed_outfit(db_session, user_id, ["navy", "red"], day=1)
        await _seed_outfit(db_session, user_id, ["gray", "navy"], day=2)

        profile = await LearningService(db_session).recompute_learning_profile(user_id)

        assert profile.learned_occasion_patterns["work"]["preferred_colors"] == [
            "navy",
            "gray",
            "red",
        ]


class TestInsightMessage:
    @pytest.mark.parametrize(
        ("category", "insight_type", "supporting_data", "expected"),
        [
            (
                "color",
                "positive",
                {"color": "navy", "score": 0.6},
                ("insightColorLoved", {"color": "navy"}),
            ),
            (
                "color",
                "negative",
                {"colors": ["orange", "pink"]},
                ("insightColorAvoided", {"color": "orange"}),
            ),
            (
                "overall",
                "positive",
                {"acceptance_rate": 0.856},
                ("insightGreatMatch", {"percent": 86}),
            ),
            ("overall", "suggestion", {"acceptance_rate": 0.2}, ("insightHelpUsLearn", {})),
            (
                "style",
                "pattern",
                # JSONB returns keys shortest first, so the order read back is not by score.
                {"styles": {"casual": 0.3, "minimalist": 0.5}},
                (
                    "insightStyleLeaning",
                    {"style": "minimalist", "styles": ["minimalist", "casual"]},
                ),
            ),
        ],
    )
    def test_maps_stored_insights_to_translatable_messages(
        self, category, insight_type, supporting_data, expected
    ):
        insight = StyleInsight(
            category=category, insight_type=insight_type, supporting_data=supporting_data
        )
        assert insight_message(insight) == expected

    def test_unknown_or_incomplete_insights_have_no_message(self):
        assert insight_message(StyleInsight(category="weather", insight_type="pattern")) == (
            None,
            {},
        )
        assert insight_message(
            StyleInsight(category="color", insight_type="negative", supporting_data={})
        ) == (None, {})


@pytest.mark.asyncio
async def test_learning_api_sends_insight_keys_alongside_the_english_text(
    client, db_session, test_user, auth_headers
):
    db_session.add(
        StyleInsight(
            user_id=test_user.id,
            category="color",
            insight_type="positive",
            title="You love navy!",
            description="Your feedback shows a strong preference for navy items.",
            supporting_data={"color": "navy", "score": 0.6},
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/learning", headers=auth_headers)

    assert response.status_code == 200
    [insight] = response.json()["insights"]
    assert insight["message_key"] == "insightColorLoved"
    assert insight["message_params"] == {"color": "navy"}
    assert insight["title"] == "You love navy!"


@pytest.mark.parametrize(
    ("score", "key"),
    [
        (0.5, "stronglyLiked"),
        (0.2, "liked"),
        (0.0, "neutral"),
        (-0.3, "disliked"),
        (-0.9, "stronglyDisliked"),
    ],
)
def test_score_interpretation_keys(score, key):
    assert score_interpretation(score) == key


@pytest.mark.asyncio
async def test_learning_api_sends_colour_interpretation_keys(
    client, db_session, test_user, auth_headers
):
    db_session.add(
        UserLearningProfile(
            user_id=test_user.id,
            learned_color_scores={"navy": 0.6, "orange": -0.3},
            last_computed_at=datetime.now(UTC),
        )
    )
    await db_session.commit()

    response = await client.get("/api/v1/learning", headers=auth_headers)

    assert response.status_code == 200
    colors = response.json()["profile"]["color_preferences"]
    assert [(c["color"], c["interpretation"], c["interpretation_key"]) for c in colors] == [
        ("navy", "strongly liked", "stronglyLiked"),
        ("orange", "disliked", "disliked"),
    ]
