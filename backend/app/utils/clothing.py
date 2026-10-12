import logging
from dataclasses import dataclass
from uuid import UUID

from app.utils.garment_vocabulary import ITEM_ROLE, ROLES, WORN_ALONE_TYPES

logger = logging.getLogger(__name__)

# A suit takes its own slot rather than outer_layer so an overcoat can still go over it.
ROLE_SLOTS: dict[str, frozenset[str]] = {
    "full_body": frozenset({"base_top", "bottom"}),
    "suit": frozenset({"bottom", "suit"}),
}

# The slots an outfit must cover; a suit's own slot is optional like an outer layer.
BODY_SLOTS = frozenset({"base_top", "bottom"})


@dataclass(frozen=True)
class WardrobeComposition:
    base_tops: int = 0
    layers: int = 0
    bottoms: int = 0
    full_body: int = 0


def count_composition(type_counts: list[tuple[str | None, int]]) -> WardrobeComposition:
    """Bucket item counts by body role. Outer layers, footwear and accessories are ignored."""
    buckets = {"base_top": 0, "mid_layer": 0, "bottom": 0, "full_body": 0}
    for item_type, count in type_counts:
        role = ITEM_ROLE.get((item_type or "").lower())
        if role in buckets:
            buckets[role] += count
    return WardrobeComposition(
        base_tops=buckets["base_top"],
        layers=buckets["mid_layer"],
        bottoms=buckets["bottom"],
        full_body=buckets["full_body"],
    )


def _slots_for_type(item_type: str) -> frozenset[str]:
    role = ITEM_ROLE.get(item_type)
    if not role or role == "accessory":
        return frozenset()
    return ROLE_SLOTS.get(role, frozenset({role}))


def covered_body_slots(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> set[str]:
    return {
        slot
        for iid in item_ids
        for slot in _slots_for_type(item_type_map.get(iid, ""))
        if slot in BODY_SLOTS
    }


def deduplicate_by_body_slot(
    item_ids: list[UUID],
    item_type_map: dict[UUID, str],
    mandatory_item_ids: set[UUID] | None = None,
) -> list[UUID]:
    requested = mandatory_item_ids or set()

    # A mandatory item only claims its slots if the caller actually passed it in item_ids;
    # one that never made the candidate list must not block the items that did.
    # Mandatory items compete with each other too, first in list order wins, because two
    # shirts or a dress plus trousers is an unwearable outfit however it was requested.
    # Multi-slot items (dress, suit) then claim before single-slot ones, so a dress wins
    # over separates wherever it appears in the list.
    mandatory = [iid for iid in item_ids if iid in requested]
    rest = [iid for iid in item_ids if iid not in requested]
    multi_slot = [iid for iid in rest if len(_slots_for_type(item_type_map.get(iid, ""))) > 1]
    multi_slot_ids = set(multi_slot)
    single_slot = [iid for iid in rest if iid not in multi_slot_ids]

    claimed: dict[str, UUID] = {}
    kept: set[UUID] = set()
    for iid in mandatory + multi_slot + single_slot:
        item_type = item_type_map.get(iid, "")
        slots = _slots_for_type(item_type)
        taken = next((slot for slot in sorted(slots) if slot in claimed), None)
        if taken:
            logger.warning(
                f"Removing {item_type} item {iid}: {taken} already filled by {claimed[taken]}"
            )
            continue
        for slot in slots:
            claimed[slot] = iid
        kept.add(iid)
    return [iid for iid in item_ids if iid in kept]


# A coat or blazer over nothing does not dress the upper body; only the types the
# vocabulary marks worn_alone (a hoodie) stand in for a top.
REGION_ROLES: dict[str, frozenset[str]] = {
    "upper": frozenset({"base_top", "suit", "full_body"}),
    "lower": frozenset({"bottom", "suit", "full_body"}),
    "feet": frozenset({"footwear"}),
}


def _regions(item_type: str) -> set[str]:
    role = ITEM_ROLE.get(item_type)
    covered = {region for region, roles in REGION_ROLES.items() if role in roles}
    if item_type in WORN_ALONE_TYPES:
        covered.add("upper")
    return covered


def _covered(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> set[str]:
    return set().union(*(_regions(item_type_map.get(iid, "")) for iid in item_ids))


def has_wearable_piece(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> bool:
    # A wardrobe with nothing that dresses any region (only layers, say) still gets outfits.
    if not _covered(list(item_type_map), item_type_map):
        return bool(item_ids)
    return bool(_covered(item_ids, item_type_map))


def missing_regions(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[str]:
    """`item_type_map` must cover every candidate, because it decides which regions the
    wardrobe can fill at all."""
    worn = _covered(item_ids, item_type_map)
    available = _covered(list(item_type_map), item_type_map)
    return [region for region in REGION_ROLES if region in available and region not in worn]


def fill_missing_regions(
    item_ids: list[UUID], ranked_candidate_ids: list[UUID], item_type_map: dict[UUID, str]
) -> list[UUID]:
    filled = list(item_ids)
    still_missing = set(missing_regions(item_ids, item_type_map))
    claimed = set().union(*(_slots_for_type(item_type_map.get(iid, "")) for iid in filled))
    for region in REGION_ROLES:
        if region not in still_missing:
            continue
        # A piece may only cover regions that are still missing and take free slots, so
        # that a dress never lands on trousers and a hoodie never goes under a coat.
        fits = [
            iid
            for iid in ranked_candidate_ids
            if iid not in filled
            and region in _regions(item_type_map.get(iid, ""))
            and _regions(item_type_map.get(iid, "")) <= still_missing
            and not _slots_for_type(item_type_map.get(iid, "")) & claimed
        ]
        # A real top goes before a layer worn alone, because the AI was asked for a top.
        pick = next((iid for iid in fits if item_type_map[iid] not in WORN_ALONE_TYPES), None)
        pick = pick or next(iter(fits), None)
        if pick is not None:
            logger.info(f"Adding {item_type_map[pick]} item {pick}: outfit had no {region} piece")
            filled.append(pick)
            still_missing -= _regions(item_type_map[pick])
            claimed |= _slots_for_type(item_type_map[pick])
    return filled


_ROLE_SORT_INDEX: dict[str, int] = {role: idx for idx, role in enumerate(ROLES)}


def remove_legwear(
    item_ids: list[UUID], item_type_map: dict[UUID, str], keep: set[UUID]
) -> list[UUID]:
    kept = []
    for iid in item_ids:
        item_type = item_type_map.get(iid, "")
        if iid not in keep and ITEM_ROLE.get(item_type) == "legwear":
            logger.info(f"Removing {item_type} item {iid}: too warm for legwear")
            continue
        kept.append(iid)
    return kept


def canonical_item_order(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[UUID]:
    original_positions = {iid: idx for idx, iid in enumerate(item_ids)}

    def sort_key(item_id: UUID) -> tuple[int, int]:
        item_type = item_type_map.get(item_id, "")
        role = ITEM_ROLE.get(item_type)
        role_idx = _ROLE_SORT_INDEX.get(role, len(ROLES)) if role else len(ROLES)
        return (role_idx, original_positions[item_id])

    return sorted(item_ids, key=sort_key)
