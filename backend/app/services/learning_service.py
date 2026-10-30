"""
Learning service for continuous AI improvement based on user feedback.

This service implements a Netflix/Spotify-style recommendation learning system that:
1. Analyzes user feedback patterns to learn preferences
2. Tracks which item combinations work well together
3. Updates user learning profiles with computed insights
4. Generates actionable style insights
5. Integrates learned preferences into the recommendation flow
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import combinations
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem
from app.models.learning import (
    ItemPairScore,
    OutfitPerformance,
    StyleInsight,
    UserLearningProfile,
)
from app.models.outfit import Outfit, OutfitItem, OutfitStatus, UserFeedback
from app.models.preference import UserPreference
from app.utils.clothing import ITEM_ROLE
from app.utils.garment_vocabulary import canonical_primary_color
from app.utils.scales import rating_to_signed, rating_to_unit
from app.utils.signed_urls import sign_optional

logger = logging.getLogger(__name__)

# Stored rows predate item roles and use these names, so those roles keep them.
_COMPOSITION_KEYS = {"base_top": "top", "footwear": "shoes", "outer_layer": "outerwear"}


def slot_composition(item_types: Iterable[str | None]) -> dict[str, str]:
    composition: dict[str, str] = {}
    for item_type in item_types:
        normalized = (item_type or "").lower()
        role = ITEM_ROLE.get(normalized)
        if role and role != "accessory":
            composition[_COMPOSITION_KEYS.get(role, role)] = normalized
    return composition


# Ties break on the colour name so that the choice does not depend on item order. A colour seen only
# in outfits with a negative signal has a zero count and is not preferred.
def _top_occasion_colors(counts: dict[str, int]) -> list[str]:
    ranked = sorted(
        (entry for entry in counts.items() if entry[1] > 0),
        key=lambda entry: (-entry[1], entry[0]),
    )
    return [color for color, _ in ranked[:3]]


# Studio outfits stay pending with feedback.accepted set, so they must match on feedback too.
_HAS_PROFILE_SIGNAL = or_(
    Outfit.status.in_([OutfitStatus.accepted, OutfitStatus.rejected]),
    Outfit.feedback.has(UserFeedback.accepted.is_not(None)),
)


def _outfit_accepted(outfit: Outfit) -> bool:
    if outfit.status in (OutfitStatus.accepted, OutfitStatus.rejected):
        return outfit.status == OutfitStatus.accepted
    return bool(outfit.feedback and outfit.feedback.accepted)


_HAS_PAIR_SIGNAL = or_(
    UserFeedback.accepted.is_not(None),
    UserFeedback.worn_at.is_not(None),
    UserFeedback.rating.is_not(None),
)


# Postgres binds at most 32767 parameters per statement; a pair row binds 12, and a pair key 2.
_PAIR_WRITE_BATCH = 1000


def _item_pairs(item_ids: Iterable[UUID]) -> set[tuple[UUID, UUID]]:
    return {tuple(sorted(pair)) for pair in combinations(set(item_ids), 2)}


def _is_positive_pair_signal(feedback: UserFeedback) -> bool:
    if feedback.worn_at is not None:
        return True
    if feedback.rating is not None:
        intent = {True: 0.3, False: -0.3}.get(feedback.accepted, 0.0)
        return intent + rating_to_signed(feedback.rating) * 0.3 > 0
    return feedback.accepted is True


@dataclass
class _PairTally:
    times_paired: int = 0
    times_accepted: int = 0
    times_rejected: int = 0
    total_rating_sum: int = 0
    rating_count: int = 0
    times_worn: int = 0
    occasion_performance: dict[str, dict[str, int]] = field(default_factory=dict)
    weather_performance: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, feedback: UserFeedback, occasion: str, temp_bucket: str | None) -> None:
        self.times_paired += 1
        if feedback.accepted is True:
            self.times_accepted += 1
        elif feedback.accepted is False:
            self.times_rejected += 1
        if feedback.rating is not None:
            self.total_rating_sum += feedback.rating
            self.rating_count += 1
        if feedback.worn_at is not None:
            self.times_worn += 1

        positive = int(_is_positive_pair_signal(feedback))
        for performance, key in (
            (self.occasion_performance, occasion),
            (self.weather_performance, temp_bucket),
        ):
            if key is not None:
                entry = performance.setdefault(key, {"count": 0, "positive": 0})
                entry["count"] += 1
                entry["positive"] += positive


def score_interpretation(score: float) -> str:
    if score >= 0.5:
        return "stronglyLiked"
    if score >= 0.2:
        return "liked"
    if score >= -0.2:
        return "neutral"
    if score >= -0.5:
        return "disliked"
    return "stronglyDisliked"


def insight_message(insight: StyleInsight) -> tuple[str | None, dict]:
    """The learning.json key and params that render a stored insight in any language.

    Derived from supporting_data rather than stored, so insights written before clients could
    translate them render too. generate_insights must keep writing the fields read here.
    """
    data = insight.supporting_data or {}
    kind = (insight.category, insight.insight_type)
    if kind == ("color", "positive") and data.get("color"):
        return "insightColorLoved", {"color": data["color"]}
    if kind == ("color", "negative") and data.get("colors"):
        return "insightColorAvoided", {"color": data["colors"][0]}
    if kind == ("overall", "positive") and data.get("acceptance_rate") is not None:
        return "insightGreatMatch", {"percent": round(float(data["acceptance_rate"]) * 100)}
    if kind == ("overall", "suggestion"):
        return "insightHelpUsLearn", {}
    if kind == ("style", "pattern") and data.get("styles"):
        # JSONB does not keep insertion order, so rank by score again.
        styles = sorted(data["styles"], key=lambda style: data["styles"][style], reverse=True)
        return "insightStyleLeaning", {"style": styles[0], "styles": styles}
    return None, {}


class LearningService:
    ACCEPTANCE_WEIGHT = 0.4
    RATING_WEIGHT = 0.4
    WEAR_WEIGHT = 0.2

    MIN_FEEDBACK_FOR_LEARNING = 1
    MIN_PAIRS_FOR_SCORING = 2

    SCORE_DECAY_RATE = 0.995

    MANUAL_SIGNAL_MULTIPLIER: float = 1.2
    WEAR_BONUS_INCREMENT: Decimal = Decimal("0.1")
    WEAR_BONUS_CAP: Decimal = Decimal("1.0")

    def __init__(self, db: AsyncSession):
        self.db = db

    def create_synthetic_feedback(
        self,
        outfit_id: UUID,
        accepted: bool = True,
        worn_at: date | None = None,
        rating: int | None = None,
        comment: str | None = None,
    ) -> UserFeedback:
        return UserFeedback(
            outfit_id=outfit_id,
            accepted=accepted,
            worn_at=worn_at,
            rating=rating,
            comment=comment,
        )

    async def process_feedback(
        self,
        outfit_id: UUID,
        user_id: UUID,
    ) -> None:
        result = await self.db.execute(
            select(Outfit)
            .where(Outfit.id == outfit_id)
            .options(
                selectinload(Outfit.feedback),
                selectinload(Outfit.items).selectinload(OutfitItem.item),
            )
        )
        outfit = result.scalar_one_or_none()

        if not outfit or not outfit.feedback:
            return

        await self._update_outfit_performance(outfit)
        await self.rebuild_pair_scores(
            outfit.user_id, _item_pairs(oi.item_id for oi in outfit.items)
        )
        await self.db.commit()

        await self._recompute_profile(user_id)

    async def _update_outfit_performance(self, outfit: Outfit) -> None:
        """Compute and store outfit performance metrics."""
        feedback = outfit.feedback
        if not feedback:
            return

        # Compute component scores
        acceptance_score = None
        if feedback.accepted is not None:
            acceptance_score = Decimal("1.0") if feedback.accepted else Decimal("0.0")

        rating_score = None
        if feedback.rating is not None:
            rating_score = Decimal(str(rating_to_unit(feedback.rating)))

        wear_score = None
        if feedback.worn_at is not None:
            # Item was worn - good signal
            wear_score = Decimal("1.0")
            if feedback.worn_with_modifications:
                # Modifications suggest not perfect match
                wear_score = Decimal("0.7")

        # Compute overall performance score
        scores = []
        weights = []

        if acceptance_score is not None:
            scores.append(float(acceptance_score))
            weights.append(self.ACCEPTANCE_WEIGHT)

        if rating_score is not None:
            scores.append(float(rating_score))
            weights.append(self.RATING_WEIGHT)

        if wear_score is not None:
            scores.append(float(wear_score))
            weights.append(self.WEAR_WEIGHT)

        if scores:
            total_weight = sum(weights)
            performance_score = (
                sum(s * w for s, w in zip(scores, weights, strict=False)) / total_weight
            )
        else:
            performance_score = 0.5  # Neutral score if no data

        # Extract context
        weather_temp = None
        weather_condition = None
        if outfit.weather_data:
            weather_temp = int(outfit.weather_data.get("temperature", 0))
            weather_condition = outfit.weather_data.get("condition")

        # Build item composition
        item_composition = slot_composition(oi.item.type for oi in outfit.items)
        color_composition = {"primary_colors": []}

        for outfit_item in outfit.items:
            item = outfit_item.item
            if item.primary_color:
                color_composition["primary_colors"].append(item.primary_color)

        # Upsert outfit performance
        stmt = insert(OutfitPerformance).values(
            outfit_id=outfit.id,
            user_id=outfit.user_id,
            performance_score=Decimal(str(performance_score)),
            acceptance_score=acceptance_score,
            rating_score=rating_score,
            wear_score=wear_score,
            occasion=outfit.occasion,
            weather_temp=weather_temp,
            weather_condition=weather_condition,
            item_composition=item_composition,
            color_composition=color_composition,
            was_modified=feedback.worn_with_modifications,
            modification_notes=feedback.modification_notes,
            computed_at=datetime.now(UTC),
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["outfit_id"],
            set_={
                "performance_score": stmt.excluded.performance_score,
                "acceptance_score": stmt.excluded.acceptance_score,
                "rating_score": stmt.excluded.rating_score,
                "wear_score": stmt.excluded.wear_score,
                "was_modified": stmt.excluded.was_modified,
                "modification_notes": stmt.excluded.modification_notes,
                "computed_at": stmt.excluded.computed_at,
            },
        )

        await self.db.execute(stmt)

    async def rebuild_pair_scores(self, user_id: UUID, pairs: Iterable[tuple[UUID, UUID]]) -> None:
        tallies = {tuple(sorted(pair)): _PairTally() for pair in pairs}
        if not tallies:
            return
        item_ids = {item_id for pair in tallies for item_id in pair}

        result = await self.db.execute(
            select(Outfit)
            .join(Outfit.feedback)
            .where(
                Outfit.user_id == user_id,
                _HAS_PAIR_SIGNAL,
                Outfit.items.any(OutfitItem.item_id.in_(item_ids)),
            )
            .options(selectinload(Outfit.feedback), selectinload(Outfit.items))
        )
        for outfit in result.scalars().all():
            outfit_item_ids = {oi.item_id for oi in outfit.items}
            temp = (outfit.weather_data or {}).get("temperature")
            bucket = self._get_temp_bucket(temp) if temp is not None else None
            for pair in _item_pairs(outfit_item_ids) & tallies.keys():
                tallies[pair].add(outfit.feedback, outfit.occasion, bucket)

        empty = [pair for pair, tally in tallies.items() if tally.times_paired == 0]
        for start in range(0, len(empty), _PAIR_WRITE_BATCH):
            await self.db.execute(
                delete(ItemPairScore).where(
                    ItemPairScore.user_id == user_id,
                    tuple_(ItemPairScore.item1_id, ItemPairScore.item2_id).in_(
                        empty[start : start + _PAIR_WRITE_BATCH]
                    ),
                )
            )

        rows = [
            {
                "user_id": user_id,
                "item1_id": item1_id,
                "item2_id": item2_id,
                "times_paired": tally.times_paired,
                "times_accepted": tally.times_accepted,
                "times_rejected": tally.times_rejected,
                "total_rating_sum": tally.total_rating_sum,
                "rating_count": tally.rating_count,
                "occasion_performance": tally.occasion_performance,
                "weather_performance": tally.weather_performance,
                "wear_bonus": min(
                    self.WEAR_BONUS_CAP, self.WEAR_BONUS_INCREMENT * tally.times_worn
                ),
                "compatibility_score": self._compute_pair_compatibility(tally),
            }
            # Sorted so that concurrent upserts lock shared rows in the same order.
            for (item1_id, item2_id), tally in sorted(tallies.items(), key=lambda kv: kv[0])
            if tally.times_paired > 0
        ]
        for start in range(0, len(rows), _PAIR_WRITE_BATCH):
            stmt = insert(ItemPairScore).values(rows[start : start + _PAIR_WRITE_BATCH])
            stmt = stmt.on_conflict_do_update(
                constraint="uq_user_item_pair",
                set_={
                    column: stmt.excluded[column]
                    for column in rows[0]
                    if column not in ("user_id", "item1_id", "item2_id")
                }
                | {"updated_at": func.now()},
            )
            await self.db.execute(stmt)
        await self.db.flush()

    async def rebuild_all_pair_scores(self, user_id: UUID) -> None:
        stored = await self.db.execute(
            select(ItemPairScore.item1_id, ItemPairScore.item2_id).where(
                ItemPairScore.user_id == user_id
            )
        )
        pairs = {tuple(row) for row in stored.all()}

        result = await self.db.execute(
            select(Outfit)
            .join(Outfit.feedback)
            .where(Outfit.user_id == user_id, _HAS_PAIR_SIGNAL)
            .options(selectinload(Outfit.items))
        )
        for outfit in result.scalars().all():
            pairs.update(_item_pairs(oi.item_id for oi in outfit.items))

        await self.rebuild_pair_scores(user_id, pairs)

    async def process_item_diff(
        self, outfit: Outfit, removed_pairs: set[tuple[UUID, UUID]]
    ) -> None:
        current = _item_pairs(oi.item_id for oi in outfit.items)
        await self.rebuild_pair_scores(outfit.user_id, current | removed_pairs)

    def _get_temp_bucket(self, temp: float) -> str:
        if temp < 5:
            return "cold"
        elif temp < 15:
            return "cool"
        elif temp < 25:
            return "mild"
        else:
            return "hot"

    def _compute_pair_compatibility(self, pair: _PairTally) -> Decimal:
        """Compute overall compatibility score for an item pair."""
        if pair.times_paired < self.MIN_PAIRS_FOR_SCORING:
            return Decimal("0.0")  # Not enough data

        # Acceptance rate component
        total_responses = pair.times_accepted + pair.times_rejected
        if total_responses > 0:
            acceptance_rate = pair.times_accepted / total_responses
        else:
            acceptance_rate = 0.5

        # Rating component
        if pair.rating_count > 0:
            avg_rating = pair.total_rating_sum / pair.rating_count
            rating_score = rating_to_unit(avg_rating)
        else:
            rating_score = 0.5

        # Combine scores
        score = (acceptance_rate * 0.6 + rating_score * 0.4) * 2 - 1  # Scale to -1 to 1

        return Decimal(str(round(score, 4)))

    async def _get_feedback_count(self, user_id: UUID) -> int:
        """Get total feedback count for a user."""
        result = await self.db.execute(
            select(func.count(UserFeedback.id)).join(Outfit).where(Outfit.user_id == user_id)
        )
        return result.scalar() or 0

    async def recompute_learning_profile(self, user_id: UUID) -> UserLearningProfile:
        """
        Recompute the entire learning profile for a user.

        This analyzes all historical feedback to derive:
        - Color preferences
        - Style preferences
        - Occasion patterns
        - Weather preferences
        - Temporal patterns
        """
        logger.info(f"Recomputing learning profile for user {user_id}")
        await self.rebuild_all_pair_scores(user_id)
        return await self._recompute_profile(user_id)

    async def _recompute_profile(self, user_id: UUID) -> UserLearningProfile:
        result = await self.db.execute(
            select(Outfit)
            .where(Outfit.user_id == user_id, _HAS_PROFILE_SIGNAL)
            .options(
                selectinload(Outfit.feedback),
                selectinload(Outfit.items).selectinload(OutfitItem.item),
            )
        )
        outfits = list(result.scalars().all())

        if len(outfits) < self.MIN_FEEDBACK_FOR_LEARNING:
            logger.info(f"Not enough feedback for user {user_id} ({len(outfits)} outfits)")
            profile = await self._get_or_create_profile(user_id)
            await self.db.commit()
            return profile

        # Initialize accumulators
        color_scores: dict[str, list[float]] = {}
        style_scores: dict[str, list[float]] = {}
        occasion_patterns: dict[str, dict] = {}
        weather_prefs: dict[str, dict] = {}

        total_accepted = 0
        total_rejected = 0
        rating_sum = 0
        rating_count = 0
        comfort_sum = 0
        comfort_count = 0
        style_sum = 0
        style_count = 0

        for outfit in outfits:
            # Determine signal from this outfit
            signal = self._get_outfit_signal(outfit)

            # Extract features
            for oi in outfit.items:
                item = oi.item

                # Color signals
                color = canonical_primary_color(item.primary_color or "")
                if color:
                    color_scores.setdefault(color, []).append(signal)

                # Style signals
                for style in item.style or []:
                    if style not in style_scores:
                        style_scores[style] = []
                    style_scores[style].append(signal)

            # Occasion patterns
            occasion = outfit.occasion
            if occasion not in occasion_patterns:
                occasion_patterns[occasion] = {
                    "colors": {},
                    "formality": {},
                    "count": 0,
                    "positive": 0,
                }
            occasion_patterns[occasion]["count"] += 1
            if signal > 0:
                occasion_patterns[occasion]["positive"] += 1

            # Track colors per occasion
            for oi in outfit.items:
                color = canonical_primary_color(oi.item.primary_color or "")
                if color:
                    if color not in occasion_patterns[occasion]["colors"]:
                        occasion_patterns[occasion]["colors"][color] = 0
                    if signal > 0:
                        occasion_patterns[occasion]["colors"][color] += 1

            # Weather preferences
            if outfit.weather_data:
                temp = outfit.weather_data.get("temperature")
                if temp is not None:
                    bucket = self._get_temp_bucket(temp)
                    if bucket not in weather_prefs:
                        weather_prefs[bucket] = {"count": 0, "positive": 0, "layers": []}
                    weather_prefs[bucket]["count"] += 1
                    if signal > 0:
                        weather_prefs[bucket]["positive"] += 1
                    weather_prefs[bucket]["layers"].append(len(outfit.items))

            if _outfit_accepted(outfit):
                total_accepted += 1
            else:
                total_rejected += 1

            if outfit.feedback:
                if outfit.feedback.rating is not None:
                    rating_sum += outfit.feedback.rating
                    rating_count += 1
                if outfit.feedback.comfort_rating is not None:
                    comfort_sum += outfit.feedback.comfort_rating
                    comfort_count += 1
                if outfit.feedback.style_rating is not None:
                    style_sum += outfit.feedback.style_rating
                    style_count += 1

        # Compute final scores
        # Lower threshold (1) to show data early; quality improves with more feedback
        learned_color_scores = {}
        for color, signals in color_scores.items():
            if len(signals) >= 1:
                learned_color_scores[color] = round(sum(signals) / len(signals), 3)

        learned_style_scores = {}
        for style, signals in style_scores.items():
            if len(signals) >= 1:
                learned_style_scores[style] = round(sum(signals) / len(signals), 3)

        # Simplify occasion patterns
        learned_occasion_patterns = {}
        for occasion, data in occasion_patterns.items():
            if data["count"] >= 1:
                learned_occasion_patterns[occasion] = {
                    "colors": data["colors"],
                    "preferred_colors": _top_occasion_colors(data["colors"]),
                    "success_rate": round(data["positive"] / data["count"], 2),
                }

        # Simplify weather preferences
        learned_weather_prefs = {}
        for bucket, data in weather_prefs.items():
            if data["count"] >= 1:
                avg_layers = sum(data["layers"]) / len(data["layers"])
                learned_weather_prefs[bucket] = {
                    "preferred_layers": round(avg_layers, 1),
                    "success_rate": round(data["positive"] / data["count"], 2),
                }

        # Compute rates
        total_responded = total_accepted + total_rejected
        acceptance_rate = total_accepted / total_responded if total_responded > 0 else None
        avg_rating = rating_sum / rating_count if rating_count > 0 else None
        avg_comfort = comfort_sum / comfort_count if comfort_count > 0 else None
        avg_style = style_sum / style_count if style_count > 0 else None

        # Update or create profile
        profile = await self._get_or_create_profile(user_id)

        profile.learned_color_scores = learned_color_scores
        profile.learned_style_scores = learned_style_scores
        profile.learned_occasion_patterns = learned_occasion_patterns
        profile.learned_weather_preferences = learned_weather_prefs
        profile.overall_acceptance_rate = (
            Decimal(str(round(acceptance_rate, 4))) if acceptance_rate is not None else None
        )
        profile.average_overall_rating = (
            Decimal(str(round(avg_rating, 2))) if avg_rating is not None else None
        )
        profile.average_comfort_rating = (
            Decimal(str(round(avg_comfort, 2))) if avg_comfort is not None else None
        )
        profile.average_style_rating = (
            Decimal(str(round(avg_style, 2))) if avg_style is not None else None
        )
        profile.feedback_count = len(outfits)
        profile.outfits_rated = rating_count
        profile.last_computed_at = datetime.now(UTC)

        await self.db.commit()
        await self.db.refresh(profile)

        logger.info(f"Learning profile updated for user {user_id}")

        return profile

    def _get_outfit_signal(self, outfit: Outfit) -> float:
        """Get a normalized signal (-1 to 1) from outfit feedback."""
        signal = 0.0

        if outfit.status == OutfitStatus.accepted:
            signal += 0.3
        elif outfit.status == OutfitStatus.rejected:
            signal -= 0.5

        if outfit.feedback:
            if outfit.feedback.rating is not None:
                signal += rating_to_signed(outfit.feedback.rating) * 0.4

            if outfit.feedback.worn_at is not None:
                signal += 0.3
                if outfit.feedback.worn_with_modifications:
                    signal -= 0.1

            # Strong negative signal if user explicitly said they didn't wear it
            if outfit.feedback.actually_worn is False:
                signal -= 0.4
                # Even stronger negative if they told us what they wore instead
                if outfit.feedback.wore_instead_items:
                    signal -= 0.2

        return max(-1.0, min(1.0, signal))

    async def _get_or_create_profile(self, user_id: UUID) -> UserLearningProfile:
        """Get existing profile or create a new one."""
        result = await self.db.execute(
            select(UserLearningProfile).where(UserLearningProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()

        if not profile:
            profile = UserLearningProfile(user_id=user_id)
            self.db.add(profile)
            await self.db.flush()

        return profile

    async def get_item_pair_suggestions(
        self,
        user_id: UUID,
        item_id: UUID,
        limit: int = 5,
    ) -> list[tuple[ClothingItem, float]]:
        """
        Get items that pair well with the given item.

        Returns list of (item, compatibility_score) tuples.
        """
        # Find pairs involving this item with positive scores
        result = await self.db.execute(
            select(ItemPairScore)
            .where(
                and_(
                    ItemPairScore.user_id == user_id,
                    ItemPairScore.compatibility_score > 0,
                    (ItemPairScore.item1_id == item_id) | (ItemPairScore.item2_id == item_id),
                )
            )
            .order_by(ItemPairScore.compatibility_score.desc())
            .limit(limit * 2)  # Fetch extra in case some items are unavailable
        )
        pairs = list(result.scalars().all())

        # Get the paired item IDs
        paired_ids = []
        scores = {}
        for pair in pairs:
            other_id = pair.item2_id if pair.item1_id == item_id else pair.item1_id
            paired_ids.append(other_id)
            scores[other_id] = float(pair.compatibility_score)

        if not paired_ids:
            return []

        # Fetch the items
        result = await self.db.execute(
            select(ClothingItem).where(
                and_(
                    ClothingItem.id.in_(paired_ids),
                    ClothingItem.is_archived.is_(False),
                )
            )
        )
        items = list(result.scalars().all())

        # Return with scores
        suggestions = [(item, scores[item.id]) for item in items if item.id in scores]
        suggestions.sort(key=lambda x: x[1], reverse=True)

        return suggestions[:limit]

    async def generate_insights(self, user_id: UUID) -> list[StyleInsight]:
        """Generate human-readable insights about the user's style."""
        profile = await self._get_or_create_profile(user_id)

        if not profile.last_computed_at or profile.feedback_count < self.MIN_FEEDBACK_FOR_LEARNING:
            return []

        insights = []
        now = datetime.now(UTC)
        expiry = now + timedelta(days=30)

        # Color insights
        if profile.color_scores:
            top_colors = sorted(
                profile.color_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )

            if top_colors and top_colors[0][1] > 0.3:
                best_color = top_colors[0][0]
                insights.append(
                    StyleInsight(
                        user_id=user_id,
                        category="color",
                        insight_type="positive",
                        title=f"You love {best_color}!",
                        description=f"Your feedback shows a strong preference for {best_color} items. We'll prioritize these in your recommendations.",
                        confidence=Decimal(str(min(0.95, abs(top_colors[0][1])))),
                        supporting_data={"color": best_color, "score": top_colors[0][1]},
                        expires_at=expiry,
                    )
                )

            # Look for avoided colors
            avoided = [c for c, s in profile.color_scores.items() if s < -0.3]
            if avoided:
                insights.append(
                    StyleInsight(
                        user_id=user_id,
                        category="color",
                        insight_type="negative",
                        title=f"Not a fan of {avoided[0]}",
                        description=f"You tend to reject outfits with {avoided[0]}. We'll suggest alternatives.",
                        confidence=Decimal("0.7"),
                        supporting_data={"colors": avoided},
                        expires_at=expiry,
                    )
                )

        # Acceptance rate insights
        if profile.overall_acceptance_rate is not None:
            rate = float(profile.overall_acceptance_rate)
            if rate > 0.8:
                insights.append(
                    StyleInsight(
                        user_id=user_id,
                        category="overall",
                        insight_type="positive",
                        title="Great match!",
                        description=f"You accept {rate * 100:.0f}% of our suggestions. We're learning your style well!",
                        confidence=Decimal("0.9"),
                        supporting_data={"acceptance_rate": rate},
                        expires_at=expiry,
                    )
                )
            elif rate < 0.4:
                insights.append(
                    StyleInsight(
                        user_id=user_id,
                        category="overall",
                        insight_type="suggestion",
                        title="Help us learn your style",
                        description="You've rejected many suggestions. Consider updating your preferences to help us improve.",
                        confidence=Decimal("0.8"),
                        supporting_data={"acceptance_rate": rate},
                        expires_at=expiry,
                    )
                )

        # Style insights
        if profile.style_scores:
            top_styles = sorted(
                profile.style_scores.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:2]
            if top_styles and top_styles[0][1] > 0.2:
                insights.append(
                    StyleInsight(
                        user_id=user_id,
                        category="style",
                        insight_type="pattern",
                        title=f"Your style: {top_styles[0][0]}",
                        description=f"Based on your feedback, you gravitate towards {', '.join(s for s, _ in top_styles)} styles.",
                        confidence=Decimal(str(min(0.9, abs(top_styles[0][1])))),
                        supporting_data={"styles": dict(top_styles)},
                        expires_at=expiry,
                    )
                )

        # Save insights to database
        for insight in insights:
            self.db.add(insight)

        await self.db.commit()

        return insights

    async def get_active_insights(self, user_id: UUID) -> list[StyleInsight]:
        """Get all active (non-expired, non-acknowledged) insights for a user."""
        now = datetime.now(UTC)

        result = await self.db.execute(
            select(StyleInsight)
            .where(
                and_(
                    StyleInsight.user_id == user_id,
                    StyleInsight.is_acknowledged.is_(False),
                    (StyleInsight.expires_at.is_(None)) | (StyleInsight.expires_at > now),
                )
            )
            .order_by(StyleInsight.created_at.desc())
        )

        return list(result.scalars().all())

    async def acknowledge_insight(self, user_id: UUID, insight_id: UUID) -> bool:
        """Mark an insight as acknowledged by the user."""
        result = await self.db.execute(
            select(StyleInsight).where(
                and_(
                    StyleInsight.id == insight_id,
                    StyleInsight.user_id == user_id,
                )
            )
        )
        insight = result.scalar_one_or_none()

        if not insight:
            return False

        insight.is_acknowledged = True
        insight.acknowledged_at = datetime.now(UTC)
        await self.db.commit()

        return True

    async def get_best_item_pairs(
        self,
        user_id: UUID,
        limit: int = 10,
    ) -> list[dict]:
        """Get the best performing item pairs for a user."""
        result = await self.db.execute(
            select(ItemPairScore)
            .where(
                and_(
                    ItemPairScore.user_id == user_id,
                    ItemPairScore.compatibility_score > 0,
                    ItemPairScore.times_paired >= self.MIN_PAIRS_FOR_SCORING,
                )
            )
            .options(
                selectinload(ItemPairScore.item1),
                selectinload(ItemPairScore.item2),
            )
            .order_by(ItemPairScore.compatibility_score.desc())
            .limit(limit)
        )
        pairs = list(result.scalars().all())

        return [
            {
                "item1": {
                    "id": str(p.item1.id),
                    "type": p.item1.type,
                    "name": p.item1.name,
                    "primary_color": p.item1.primary_color,
                    "thumbnail_path": p.item1.thumbnail_path,
                    "thumbnail_url": sign_optional(p.item1.thumbnail_path),
                },
                "item2": {
                    "id": str(p.item2.id),
                    "type": p.item2.type,
                    "name": p.item2.name,
                    "primary_color": p.item2.primary_color,
                    "thumbnail_path": p.item2.thumbnail_path,
                    "thumbnail_url": sign_optional(p.item2.thumbnail_path),
                },
                "compatibility_score": float(p.compatibility_score),
                "times_paired": p.times_paired,
                "times_accepted": p.times_accepted,
            }
            for p in pairs
        ]

    async def apply_learning_to_preferences(
        self,
        user_id: UUID,
        threshold: float = 0.5,
    ) -> dict:
        """
        Apply learned preferences to user's explicit preferences.

        This allows the system to automatically update user preferences
        based on what it has learned. Returns what was updated.
        """
        profile = await self._get_or_create_profile(user_id)

        if not profile.last_computed_at:
            return {"updated": False, "reason": "No learning data available"}

        # Get user's current preferences
        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()

        if not prefs:
            return {"updated": False, "reason": "No preferences found"}

        updates = {}

        # Suggest adding learned favorite colors
        if profile.color_scores:
            strong_likes = [
                c
                for c, s in profile.color_scores.items()
                if s >= threshold and c not in (prefs.color_favorites or [])
            ]
            if strong_likes:
                updates["suggested_favorite_colors"] = strong_likes

            strong_dislikes = [
                c
                for c, s in profile.color_scores.items()
                if s <= -threshold and c not in (prefs.color_avoid or [])
            ]
            if strong_dislikes:
                updates["suggested_avoid_colors"] = strong_dislikes

        return {
            "updated": bool(updates),
            "suggestions": updates,
            "confidence": float(profile.overall_acceptance_rate)
            if profile.overall_acceptance_rate is not None
            else None,
        }
