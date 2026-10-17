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


# Each region is dressed by whatever takes its slot, so a one-piece covers upper and lower
# while a suit covers only lower and still needs a top. A coat or blazer over nothing does
# not dress the upper body; only the types the vocabulary marks worn_alone (a hoodie) stand
# in for a top.
REGION_SLOTS: dict[str, str] = {"upper": "base_top", "lower": "bottom", "feet": "footwear"}


def _regions(item_type: str) -> set[str]:
    slots = _slots_for_type(item_type)
    covered = {region for region, slot in REGION_SLOTS.items() if slot in slots}
    if item_type in WORN_ALONE_TYPES:
        covered.add("upper")
    return covered


def covered_regions(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> set[str]:
    return set().union(*(_regions(item_type_map.get(iid, "")) for iid in item_ids))


LAYER_ROLES = frozenset({"mid_layer", "outer_layer"})


def has_wearable_piece(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> bool:
    # A wardrobe with nothing that dresses any region still gets outfits from its layers,
    # but a bag or tights alone is never an outfit.
    if not covered_regions(list(item_type_map), item_type_map):
        return any(ITEM_ROLE.get(item_type_map.get(iid, "")) in LAYER_ROLES for iid in item_ids)
    return bool(covered_regions(item_ids, item_type_map))


def missing_regions(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[str]:
    """`item_type_map` must cover every candidate, because it decides which regions the
    wardrobe can fill at all."""
    worn = covered_regions(item_ids, item_type_map)
    available = covered_regions(list(item_type_map), item_type_map)
    return [region for region in REGION_SLOTS if region in available and region not in worn]


def _fill_options(
    region: str,
    remaining: frozenset[str],
    rank: dict[UUID, int],
    item_type_map: dict[UUID, str],
    taken: frozenset[UUID],
    claimed: frozenset[str],
) -> list[tuple[UUID, int]]:
    # A piece may only cover regions that are still missing and take free slots, so that
    # a dress never lands on trousers and a hoodie never goes under a coat.
    fits = [
        iid
        for iid in rank
        if iid not in taken
        and region in _regions(item_type_map.get(iid, ""))
        and _regions(item_type_map.get(iid, "")) <= remaining
        and not _slots_for_type(item_type_map.get(iid, "")) & claimed
    ]
    best: dict[frozenset[str], tuple[UUID, int]] = {}
    for iid in fits:
        best.setdefault(frozenset(_regions(item_type_map[iid])), (iid, rank[iid]))
    single = best.get(frozenset({region}))
    # A real top goes before a better-ranked layer worn alone, because the AI was asked
    # for a top. It competes at the layer's rank, so that swapping in a weaker top never
    # hands the win to a one-piece the layer would have beaten.
    if single is not None and item_type_map[single[0]] in WORN_ALONE_TYPES:
        top = next(
            (
                iid
                for iid in fits
                if _regions(item_type_map[iid]) == {region}
                and item_type_map[iid] not in WORN_ALONE_TYPES
            ),
            None,
        )
        if top is not None:
            best[frozenset({region})] = (top, single[1])
    return list(best.values())


def _best_fill(
    remaining: frozenset[str],
    rank: dict[UUID, int],
    item_type_map: dict[UUID, str],
    taken: frozenset[UUID],
    claimed: frozenset[str],
) -> list[tuple[UUID, int]]:
    if not remaining:
        return []
    region = next(r for r in REGION_SLOTS if r in remaining)
    plans = [_best_fill(remaining - {region}, rank, item_type_map, taken, claimed)]
    for pick, pick_rank in _fill_options(region, remaining, rank, item_type_map, taken, claimed):
        pick_type = item_type_map[pick]
        rest = _best_fill(
            remaining - _regions(pick_type),
            rank,
            item_type_map,
            taken | {pick},
            claimed | _slots_for_type(pick_type),
        )
        plans.append([(pick, pick_rank), *rest])
    # The plan that dresses the most regions wins, then the one whose picks rank best,
    # compared in region order (upper first).
    return min(
        plans,
        key=lambda plan: (
            len(remaining - covered_regions([iid for iid, _ in plan], item_type_map)),
            [pick_rank for _, pick_rank in plan],
        ),
    )


def can_complete_outfit(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> bool:
    # Looser than the fill, because an AI answer may add a piece that also covers a region
    # already dressed (a hoodie over a dress); only free slots limit it. Items of one type
    # share slots and regions, so searching types keeps this cheap on a large wardrobe.
    others = {t for iid, t in item_type_map.items() if iid not in item_ids}

    def reachable(remaining: frozenset[str], claimed: frozenset[str]) -> bool:
        if not remaining:
            return True
        region = next(r for r in REGION_SLOTS if r in remaining)
        return any(
            reachable(remaining - _regions(t), claimed | _slots_for_type(t))
            for t in others
            if region in _regions(t) and not _slots_for_type(t) & claimed
        )

    claimed = frozenset().union(*(_slots_for_type(item_type_map.get(iid, "")) for iid in item_ids))
    return reachable(frozenset(missing_regions(item_ids, item_type_map)), claimed)


def fill_missing_regions(
    item_ids: list[UUID], ranked_candidate_ids: list[UUID], item_type_map: dict[UUID, str]
) -> list[UUID]:
    claimed = frozenset().union(*(_slots_for_type(item_type_map.get(iid, "")) for iid in item_ids))
    plan = _best_fill(
        frozenset(missing_regions(item_ids, item_type_map)),
        {iid: n for n, iid in enumerate(ranked_candidate_ids)},
        item_type_map,
        frozenset(item_ids),
        claimed,
    )
    added = [iid for iid, _ in plan]
    for iid in added:
        covered = _regions(item_type_map[iid])
        regions = ", ".join(r for r in REGION_SLOTS if r in covered)
        logger.info(f"Adding {item_type_map[iid]} item {iid}: outfit had no {regions} piece")
    return [*item_ids, *added]


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
