import json
import logging
import re
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.item import ClothingItem, ItemStatus
from app.models.outfit import FamilyOutfitRating, Outfit, OutfitItem, OutfitSource, OutfitStatus
from app.models.user import User
from app.services.ai_service import AIService
from app.utils.prompts import load_prompt
from app.utils.timezone import get_user_today

logger = logging.getLogger(__name__)

PAIRING_PROMPT_TEMPLATE = load_prompt("item_pairing")


class PairingService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_source_item(self, user_id: UUID, item_id: UUID) -> ClothingItem | None:
        result = await self.db.execute(
            select(ClothingItem).where(
                and_(
                    ClothingItem.id == item_id,
                    ClothingItem.user_id == user_id,
                    ClothingItem.status == ItemStatus.ready,
                    ClothingItem.is_archived.is_(False),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_available_items(self, user: User, exclude_item_id: UUID) -> list[ClothingItem]:
        query = select(ClothingItem).where(
            and_(
                ClothingItem.user_id == user.id,
                ClothingItem.status == ItemStatus.ready,
                ClothingItem.is_archived.is_(False),
                ClothingItem.id != exclude_item_id,
            )
        )
        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _format_item_description(self, item: ClothingItem) -> str:
        parts = []

        # Type and subtype
        item_type = item.type or "item"
        if item.subtype:
            parts.append(f"{item.subtype} ({item_type})")
        else:
            parts.append(item_type)

        # Colors
        if item.colors and len(item.colors) > 1:
            parts.append(f"colors: {', '.join(item.colors)}")
        elif item.primary_color:
            parts.append(item.primary_color)

        # Pattern
        if item.pattern and item.pattern != "solid":
            parts.append(item.pattern)

        # Material
        if item.material:
            parts.append(item.material)

        # Formality
        if item.formality:
            parts.append(item.formality)

        # Name if set
        if item.name:
            parts.insert(0, f'"{item.name}"')

        return " | ".join(parts)

    def _format_items_for_prompt(
        self, source_item: ClothingItem, items: list[ClothingItem]
    ) -> tuple[str, str, int, dict[int, UUID]]:
        # Source item is always number 1
        source_number = 1
        source_description = self._format_item_description(source_item)

        number_map: dict[int, UUID] = {source_number: source_item.id}
        lines = []

        for i, item in enumerate(items, 2):
            number_map[i] = item.id
            desc = self._format_item_description(item)
            lines.append(f"[{i}] {desc}")

        items_text = "\n".join(lines)
        return source_description, items_text, source_number, number_map

    def _parse_ai_response(self, content: str) -> list[dict]:
        def strip_comments(json_str: str) -> str:
            json_str = re.sub(r"//[^\n]*", "", json_str)
            json_str = re.sub(r"/\*[\s\S]*?\*/", "", json_str)
            return json_str

        # Try direct JSON parse
        try:
            result = json.loads(content.strip())
            if isinstance(result, list):
                return result
            # If it's a dict with pairings array
            if isinstance(result, dict) and "pairings" in result:
                return result["pairings"]
            return [result]
        except json.JSONDecodeError:
            pass

        # Try with comments stripped
        try:
            result = json.loads(strip_comments(content.strip()))
            if isinstance(result, list):
                return result
            return [result]
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        if json_match:
            extracted = json_match.group(1)
            try:
                result = json.loads(extracted)
                if isinstance(result, list):
                    return result
                return [result]
            except json.JSONDecodeError:
                pass

        # Try finding JSON array with balanced brackets
        start_idx = content.find("[")
        if start_idx != -1:
            bracket_count = 0
            for i, char in enumerate(content[start_idx:], start_idx):
                if char == "[":
                    bracket_count += 1
                elif char == "]":
                    bracket_count -= 1
                    if bracket_count == 0:
                        json_str = content[start_idx : i + 1]
                        try:
                            result = json.loads(json_str)
                            if isinstance(result, list):
                                return result
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"Could not parse AI response as JSON: {content[:200]}")

    async def generate_pairings(
        self,
        user: User,
        source_item_id: UUID,
        num_pairings: int = 3,
    ) -> list[Outfit]:
        num_pairings = max(1, min(5, num_pairings))

        # Get source item
        source_item = await self.get_source_item(user.id, source_item_id)
        if not source_item:
            raise ValueError("Source item not found or not available")

        # Get available items
        available_items = await self.get_available_items(user, source_item_id)
        if len(available_items) < 2:
            raise InsufficientItemsError(
                "Not enough items in wardrobe for pairing. Add more items."
            )

        # Get user preferences for AI endpoints
        preferences = user.preferences
        ai_endpoints = None
        if preferences and preferences.ai_endpoints:
            ai_endpoints = preferences.ai_endpoints
        ai_service = AIService(endpoints=ai_endpoints)

        # Format items for prompt
        source_desc, items_text, source_num, number_map = self._format_items_for_prompt(
            source_item, available_items
        )

        # Build prompt
        prompt = PAIRING_PROMPT_TEMPLATE.format(
            source_number=source_num,
            source_description=source_desc,
            items_text=items_text,
            num_pairings=num_pairings,
        )

        logger.info(
            f"Generating {num_pairings} pairings for user {user.id}, "
            f"source item: {source_item_id}, available items: {len(available_items)}"
        )

        # Call AI
        try:
            result = await ai_service.generate_text(prompt, return_metadata=True)
            logger.info(f"AI pairings generated (model: {result.model})")
            logger.debug(f"AI raw response: {result.content[:500]}")
            pairings_data = self._parse_ai_response(result.content)
        except Exception as e:
            logger.error(f"AI pairing generation failed: {e}")
            raise AIGenerationError(
                "AI service is not available. Check your AI endpoint configuration."
            ) from e

        # Create outfit records for each pairing
        created_outfits = []
        user_today = get_user_today(user)

        for pairing in pairings_data[:num_pairings]:
            # Get item numbers from the pairing
            selected_numbers = pairing.get("items", [])
            valid_ids = []

            for num in selected_numbers:
                try:
                    num_int = int(num)
                    if num_int in number_map:
                        valid_ids.append(number_map[num_int])
                    else:
                        logger.warning(f"AI selected invalid item number: {num}")
                except (ValueError, TypeError):
                    logger.warning(f"AI returned non-numeric item: {num}")

            # Ensure source item is included
            if source_item.id not in valid_ids:
                valid_ids.insert(0, source_item.id)

            if len(valid_ids) < 2:
                logger.warning("Pairing has too few valid items, skipping")
                continue

            # Create outfit
            outfit = Outfit(
                user_id=user.id,
                occasion="pairing",
                scheduled_for=user_today,
                source=OutfitSource.pairing,
                source_item_id=source_item_id,
                status=OutfitStatus.pending,
                reasoning=pairing.get("headline"),
                style_notes=pairing.get("styling_tip"),
                ai_raw_response=pairing,
            )
            self.db.add(outfit)
            await self.db.flush()

            # Add outfit items
            for position, item_id in enumerate(valid_ids):
                outfit_item = OutfitItem(
                    outfit_id=outfit.id,
                    item_id=item_id,
                    position=position,
                )
                self.db.add(outfit_item)

            created_outfits.append(outfit)

        await self.db.commit()

        # Reload with relationships
        loaded_outfits = []
        for outfit in created_outfits:
            result = await self.db.execute(
                select(Outfit)
                .where(Outfit.id == outfit.id)
                .options(
                    selectinload(Outfit.items).selectinload(OutfitItem.item),
                    selectinload(Outfit.feedback),
                    selectinload(Outfit.source_item),
                    selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
                )
            )
            loaded_outfits.append(result.scalar_one())

        logger.info(f"Created {len(loaded_outfits)} pairings for item {source_item_id}")
        return loaded_outfits

    async def get_pairings_for_item(
        self,
        user_id: UUID,
        source_item_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Outfit], int]:
        # Base query
        base_query = select(Outfit).where(
            and_(
                Outfit.user_id == user_id,
                Outfit.source == OutfitSource.pairing,
                Outfit.source_item_id == source_item_id,
            )
        )

        # Count
        count_result = await self.db.execute(
            select(Outfit.id).where(
                and_(
                    Outfit.user_id == user_id,
                    Outfit.source == OutfitSource.pairing,
                    Outfit.source_item_id == source_item_id,
                )
            )
        )
        total = len(count_result.all())

        # Fetch with pagination
        query = (
            base_query.options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.source_item),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
            .order_by(Outfit.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(query)
        outfits = list(result.scalars().all())

        return outfits, total

    async def get_all_pairings(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
        source_type: str | None = None,
    ) -> tuple[list[Outfit], int]:
        # Base conditions
        conditions = [
            Outfit.user_id == user_id,
            Outfit.source == OutfitSource.pairing,
        ]

        # Filter by source item type if specified
        if source_type:
            conditions.append(Outfit.source_item.has(ClothingItem.type == source_type))

        # Count
        count_query = select(Outfit.id).where(and_(*conditions))
        count_result = await self.db.execute(count_query)
        total = len(count_result.all())

        # Fetch with pagination
        query = (
            select(Outfit)
            .where(and_(*conditions))
            .options(
                selectinload(Outfit.items).selectinload(OutfitItem.item),
                selectinload(Outfit.feedback),
                selectinload(Outfit.source_item),
                selectinload(Outfit.family_ratings).selectinload(FamilyOutfitRating.user),
            )
            .order_by(Outfit.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        result = await self.db.execute(query)
        outfits = list(result.scalars().all())

        return outfits, total


class InsufficientItemsError(Exception):
    pass


class AIGenerationError(Exception):
    pass
