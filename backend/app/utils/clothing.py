import logging
from uuid import UUID

logger = logging.getLogger(__name__)

# Body-slot mapping derived from the type vocabulary in clothing_analysis.txt.
# Used to prevent outfits containing multiple items in the same slot
# (e.g. shorts + pants).
BODY_SLOT_MAP: dict[str, str] = {
    "shirt": "top",
    "t-shirt": "top",
    "top": "top",
    "blouse": "top",
    "polo": "top",
    "tank-top": "top",
    "sweater": "top",
    "hoodie": "top",
    "cardigan": "top",
    "vest": "top",
    "pants": "bottom",
    "jeans": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "dress": "full-body",
    "jumpsuit": "full-body",
    "shoes": "shoes",
    "sneakers": "shoes",
    "boots": "shoes",
    "sandals": "shoes",
    "jacket": "outerwear",
    "coat": "outerwear",
    "blazer": "outerwear",
    "socks": "socks",
    "tie": "neckwear",
}


def deduplicate_by_body_slot(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[UUID]:
    seen_slots: dict[str, UUID] = {}
    result: list[UUID] = []
    has_full_body = any(
        BODY_SLOT_MAP.get(item_type_map.get(iid, "")) == "full-body" for iid in item_ids
    )
    for iid in item_ids:
        item_type = item_type_map.get(iid, "")
        slot = BODY_SLOT_MAP.get(item_type)
        if not slot:
            result.append(iid)
            continue
        if has_full_body and slot in ("top", "bottom"):
            logger.warning(f"Removing {item_type} item {iid}: full-body item present")
            continue
        if slot in seen_slots:
            logger.warning(
                f"Removing duplicate {slot} item {iid} ({item_type}): "
                f"slot already filled by {seen_slots[slot]}"
            )
            continue
        seen_slots[slot] = iid
        result.append(iid)
    return result
