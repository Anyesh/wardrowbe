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
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from itertools import combinations
from uuid import UUID

from sqlalchemy import and_, func, select
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
from app.utils.signed_urls import sign_image_url

logger = logging.getLogger(__name__)


class LearningService:
    """Service for learning from user feedback and improving recommendations."""

    # Weights for computing performance scores
    ACCEPTANCE_WEIGHT = 0.4
    RATING_WEIGHT = 0.4
    WEAR_WEIGHT = 0.2

    # Minimum data points needed for reliable learning
    # Low threshold to show data early; quality improves with more feedback
    MIN_FEEDBACK_FOR_LEARNING = 1
    MIN_PAIRS_FOR_SCORING = 2

    # Score decay for older feedback (per day)
    SCORE_DECAY_RATE = 0.995

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_feedback(
        self,
        outfit_id: UUID,
        user_id: UUID,
    ) -> None:
        """
        Process new feedback and update learning models.

        This is called whenever a user submits feedback on an outfit.
        It updates:
        1. OutfitPerformance record
        2. ItemPairScore records for items in the outfit
        3. "Wore instead" items get positive signals
        4. Triggers profile recomputation if threshold reached
        """
        # Get outfit with all related data
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

        # Update outfit performance
        await self._update_outfit_performance(outfit)

        # Update item pair scores
        await self._update_item_pair_scores(outfit)

        # Process "wore instead" items - these get POSITIVE signals
        # because user actively chose them over our recommendation
        if outfit.feedback.wore_instead_items:
            await self._process_wore_instead(outfit)

        await self.db.commit()

        # Always recompute learning profile after feedback
        # This ensures the user sees updated data immediately
        logger.info(f"Triggering learning profile recomputation for user {user_id}")
        await self.recompute_learning_profile(user_id)

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
            # Normalize 1-5 rating to 0-1
            rating_score = Decimal(str((feedback.rating - 1) / 4))

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
            performance_score = sum(s * w for s, w in zip(scores, weights, strict=True)) / total_weight
        else:
            performance_score = 0.5  # Neutral score if no data

        # Extract context
        weather_temp = None
        weather_condition = None
        if outfit.weather_data:
            weather_temp = int(outfit.weather_data.get("temperature", 0))
            weather_condition = outfit.weather_data.get("condition")

        # Build item composition
        item_composition = {}
        color_composition = {"primary_colors": []}

        for outfit_item in outfit.items:
            item = outfit_item.item
            item_type = item.type.lower() if item.type else "unknown"

            # Categorize by type
            if item_type in ["shirt", "blouse", "t-shirt", "sweater", "top"]:
                item_composition["top"] = item_type
            elif item_type in ["pants", "jeans", "skirt", "shorts"]:
                item_composition["bottom"] = item_type
            elif item_type in ["sneakers", "boots", "heels", "shoes", "sandals"]:
                item_composition["shoes"] = item_type
            elif item_type in ["jacket", "coat", "outerwear"]:
                item_composition["outerwear"] = item_type

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
            computed_at=datetime.now(timezone.utc),
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

    async def _update_item_pair_scores(self, outfit: Outfit) -> None:
        """Update compatibility scores for all item pairs in the outfit."""
        feedback = outfit.feedback
        if not feedback:
            return

        items = [oi.item for oi in outfit.items]
        if len(items) < 2:
            return

        # Determine feedback signal
        is_positive = False
        signal_strength = 0.0

        if feedback.accepted is not None:
            if feedback.accepted:
                is_positive = True
                signal_strength = 0.3
            else:
                signal_strength = -0.3

        if feedback.rating is not None:
            rating_signal = (feedback.rating - 3) / 2  # -1 to 1
            signal_strength += rating_signal * 0.3
            is_positive = signal_strength > 0

        if feedback.worn_at is not None:
            signal_strength += 0.2
            is_positive = True

        # Create all pairs (ensuring item1_id < item2_id for uniqueness)
        for item1, item2 in combinations(items, 2):
            id1, id2 = (item1.id, item2.id) if item1.id < item2.id else (item2.id, item1.id)

            # Get or create pair score
            result = await self.db.execute(
                select(ItemPairScore).where(
                    and_(
                        ItemPairScore.user_id == outfit.user_id,
                        ItemPairScore.item1_id == id1,
                        ItemPairScore.item2_id == id2,
                    )
                )
            )
            pair_score = result.scalar_one_or_none()

            if not pair_score:
                pair_score = ItemPairScore(
                    user_id=outfit.user_id,
                    item1_id=id1,
                    item2_id=id2,
                )
                self.db.add(pair_score)

            # Update counts
            pair_score.times_paired += 1

            if feedback.accepted is True:
                pair_score.times_accepted += 1
            elif feedback.accepted is False:
                pair_score.times_rejected += 1

            if feedback.rating is not None:
                pair_score.total_rating_sum += feedback.rating
                pair_score.rating_count += 1

            # Update occasion performance
            occasion = outfit.occasion
            occasion_perf = dict(pair_score.occasion_performance) if pair_score.occasion_performance else {}
            if occasion not in occasion_perf:
                occasion_perf[occasion] = {"count": 0, "positive": 0}
            occasion_perf[occasion]["count"] += 1
            if is_positive:
                occasion_perf[occasion]["positive"] += 1
            pair_score.occasion_performance = occasion_perf

            # Update weather performance
            if outfit.weather_data:
                temp = outfit.weather_data.get("temperature")
                if temp is not None:
                    temp_bucket = self._get_temp_bucket(temp)
                    weather_perf = dict(pair_score.weather_performance) if pair_score.weather_performance else {}
                    if temp_bucket not in weather_perf:
                        weather_perf[temp_bucket] = {"count": 0, "positive": 0}
                    weather_perf[temp_bucket]["count"] += 1
                    if is_positive:
                        weather_perf[temp_bucket]["positive"] += 1
                    pair_score.weather_performance = weather_perf

            # Recompute compatibility score
            pair_score.compatibility_score = self._compute_pair_compatibility(pair_score)

    async def _process_wore_instead(self, outfit: Outfit) -> None:
        """
        Process items the user wore instead of the recommendation.

        When a user rejects our outfit and tells us what they wore instead,
        we learn that those items are preferred. This creates positive pair
        scores for items they chose.
        """
        feedback = outfit.feedback
        if not feedback or not feedback.wore_instead_items:
            return

        # Get the items they wore instead
        wore_instead_ids = [UUID(item_id) for item_id in feedback.wore_instead_items]

        if len(wore_instead_ids) < 2:
            # Need at least 2 items to form a pair
            return

        # Get the actual items
        result = await self.db.execute(
            select(ClothingItem).where(ClothingItem.id.in_(wore_instead_ids))
        )
        wore_items = list(result.scalars().all())

        if len(wore_items) < 2:
            return

        logger.info(
            f"Processing 'wore instead' items for user {outfit.user_id}: "
            f"{len(wore_items)} items"
        )

        # Create positive pair scores for items they actually wore
        # These get a strong positive signal since user actively chose them
        for item1, item2 in combinations(wore_items, 2):
            id1, id2 = (item1.id, item2.id) if item1.id < item2.id else (item2.id, item1.id)

            # Get or create pair score
            result = await self.db.execute(
                select(ItemPairScore).where(
                    and_(
                        ItemPairScore.user_id == outfit.user_id,
                        ItemPairScore.item1_id == id1,
                        ItemPairScore.item2_id == id2,
                    )
                )
            )
            pair_score = result.scalar_one_or_none()

            if not pair_score:
                pair_score = ItemPairScore(
                    user_id=outfit.user_id,
                    item1_id=id1,
                    item2_id=id2,
                )
                self.db.add(pair_score)

            # Strong positive signal - user chose this over our recommendation
            pair_score.times_paired += 1
            pair_score.times_accepted += 1  # Treat as accepted since user chose it

            # Give a strong rating boost (equivalent to 5-star rating)
            pair_score.total_rating_sum += 5
            pair_score.rating_count += 1

            # Recompute compatibility
            pair_score.compatibility_score = self._compute_pair_compatibility(pair_score)

    def _get_temp_bucket(self, temp: float) -> str:
        """Get temperature bucket for grouping."""
        if temp < 5:
            return "cold"
        elif temp < 15:
            return "cool"
        elif temp < 25:
            return "mild"
        else:
            return "hot"

    def _compute_pair_compatibility(self, pair: ItemPairScore) -> Decimal:
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
            rating_score = (avg_rating - 1) / 4  # Normalize to 0-1
        else:
            rating_score = 0.5

        # Combine scores
        score = (acceptance_rate * 0.6 + rating_score * 0.4) * 2 - 1  # Scale to -1 to 1

        return Decimal(str(round(score, 4)))

    async def _get_feedback_count(self, user_id: UUID) -> int:
        """Get total feedback count for a user."""
        result = await self.db.execute(
            select(func.count(UserFeedback.id))
            .join(Outfit)
            .where(Outfit.user_id == user_id)
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

        # Get all feedbacks with outfit details
        result = await self.db.execute(
            select(Outfit)
            .where(
                and_(
                    Outfit.user_id == user_id,
                    Outfit.status.in_([OutfitStatus.accepted, OutfitStatus.rejected]),
                )
            )
            .options(
                selectinload(Outfit.feedback),
                selectinload(Outfit.items).selectinload(OutfitItem.item),
            )
        )
        outfits = list(result.scalars().all())

        if len(outfits) < self.MIN_FEEDBACK_FOR_LEARNING:
            logger.info(f"Not enough feedback for user {user_id} ({len(outfits)} outfits)")
            return await self._get_or_create_profile(user_id)

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
                if item.primary_color:
                    if item.primary_color not in color_scores:
                        color_scores[item.primary_color] = []
                    color_scores[item.primary_color].append(signal)

                # Style signals
                for style in (item.style or []):
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
                if oi.item.primary_color:
                    color = oi.item.primary_color
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

            # Aggregate statistics
            if outfit.status == OutfitStatus.accepted:
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
                # Find most successful colors for this occasion
                top_colors = sorted(
                    data["colors"].items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:3]
                learned_occasion_patterns[occasion] = {
                    "preferred_colors": [c for c, _ in top_colors],
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
        profile.overall_acceptance_rate = Decimal(str(round(acceptance_rate, 4))) if acceptance_rate else None
        profile.average_overall_rating = Decimal(str(round(avg_rating, 2))) if avg_rating else None
        profile.average_comfort_rating = Decimal(str(round(avg_comfort, 2))) if avg_comfort else None
        profile.average_style_rating = Decimal(str(round(avg_style, 2))) if avg_style else None
        profile.feedback_count = len(outfits)
        profile.outfits_rated = rating_count
        profile.last_computed_at = datetime.now(timezone.utc)

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
                # Map 1-5 to -1 to 1
                signal += (outfit.feedback.rating - 3) / 2 * 0.4

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

    async def get_learned_preferences(
        self,
        user_id: UUID,
    ) -> dict:
        """
        Get learned preferences for use in recommendations.

        Returns a dict that can be used to augment the recommendation prompt.
        """
        profile = await self._get_or_create_profile(user_id)

        if not profile.last_computed_at:
            return {}

        preferences = {}

        # Top liked colors
        if profile.learned_color_scores:
            liked_colors = sorted(
                [(c, s) for c, s in profile.learned_color_scores.items() if s > 0.2],
                key=lambda x: x[1],
                reverse=True,
            )[:5]
            disliked_colors = sorted(
                [(c, s) for c, s in profile.learned_color_scores.items() if s < -0.2],
                key=lambda x: x[1],
            )[:3]

            if liked_colors:
                preferences["learned_favorite_colors"] = [c for c, _ in liked_colors]
            if disliked_colors:
                preferences["learned_avoid_colors"] = [c for c, _ in disliked_colors]

        # Top liked styles
        if profile.learned_style_scores:
            liked_styles = sorted(
                [(s, score) for s, score in profile.learned_style_scores.items() if score > 0.2],
                key=lambda x: x[1],
                reverse=True,
            )[:3]
            if liked_styles:
                preferences["learned_preferred_styles"] = [s for s, _ in liked_styles]

        # Occasion-specific preferences
        if profile.learned_occasion_patterns:
            preferences["occasion_insights"] = profile.learned_occasion_patterns

        # Weather preferences
        if profile.learned_weather_preferences:
            preferences["weather_insights"] = profile.learned_weather_preferences

        return preferences

    async def generate_insights(self, user_id: UUID) -> list[StyleInsight]:
        """Generate human-readable insights about the user's style."""
        profile = await self._get_or_create_profile(user_id)

        if not profile.last_computed_at or profile.feedback_count < self.MIN_FEEDBACK_FOR_LEARNING:
            return []

        insights = []
        now = datetime.now(timezone.utc)
        expiry = now + timedelta(days=30)

        # Color insights
        if profile.learned_color_scores:
            top_colors = sorted(
                profile.learned_color_scores.items(),
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
            avoided = [c for c, s in profile.learned_color_scores.items() if s < -0.3]
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
                        description=f"You accept {rate*100:.0f}% of our suggestions. We're learning your style well!",
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
        if profile.learned_style_scores:
            top_styles = sorted(
                profile.learned_style_scores.items(),
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
        now = datetime.now(timezone.utc)

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
        insight.acknowledged_at = datetime.now(timezone.utc)
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
                    "thumbnail_url": sign_image_url(p.item1.thumbnail_path) if p.item1.thumbnail_path else None,
                },
                "item2": {
                    "id": str(p.item2.id),
                    "type": p.item2.type,
                    "name": p.item2.name,
                    "primary_color": p.item2.primary_color,
                    "thumbnail_path": p.item2.thumbnail_path,
                    "thumbnail_url": sign_image_url(p.item2.thumbnail_path) if p.item2.thumbnail_path else None,
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
        if profile.learned_color_scores:
            strong_likes = [
                c for c, s in profile.learned_color_scores.items()
                if s >= threshold and c not in (prefs.color_favorites or [])
            ]
            if strong_likes:
                updates["suggested_favorite_colors"] = strong_likes

            strong_dislikes = [
                c for c, s in profile.learned_color_scores.items()
                if s <= -threshold and c not in (prefs.color_avoid or [])
            ]
            if strong_dislikes:
                updates["suggested_avoid_colors"] = strong_dislikes

        return {
            "updated": bool(updates),
            "suggestions": updates,
            "confidence": float(profile.overall_acceptance_rate) if profile.overall_acceptance_rate else None,
        }
