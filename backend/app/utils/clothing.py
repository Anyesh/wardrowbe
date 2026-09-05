import logging
from uuid import UUID

logger = logging.getLogger(__name__)

ITEM_ROLE: dict[str, str] = {
    "shirt": "base_top",
    "t-shirt": "base_top",
    "blouse": "base_top",
    "polo": "base_top",
    "tank-top": "base_top",
    "top": "base_top",
    "sweater": "base_top",
    "pants": "bottom",
    "jeans": "bottom",
    "shorts": "bottom",
    "skirt": "bottom",
    "dress": "full_body",
    "jumpsuit": "full_body",
    "cardigan": "mid_layer",
    "vest": "mid_layer",
    "jacket": "outer_layer",
    "blazer": "outer_layer",
    "coat": "outer_layer",
    "hoodie": "outer_layer",
    "shoes": "footwear",
    "sneakers": "footwear",
    "boots": "footwear",
    "sandals": "footwear",
    "socks": "socks",
    "tie": "neckwear",
    "hat": "accessory",
    "scarf": "accessory",
    "belt": "accessory",
    "bag": "accessory",
    "accessories": "accessory",
}


def deduplicate_by_body_slot(
    item_ids: list[UUID],
    item_type_map: dict[UUID, str],
    mandatory_item_ids: set[UUID] | None = None,
) -> list[UUID]:
    mandatory = mandatory_item_ids or set()
    seen_roles: dict[str, UUID] = {}
    result: list[UUID] = []

    mandatory_has_full_body = any(
        ITEM_ROLE.get(item_type_map.get(iid, "")) == "full_body" for iid in mandatory
    )
    mandatory_has_separates = any(
        ITEM_ROLE.get(item_type_map.get(iid, "")) in ("base_top", "bottom") for iid in mandatory
    )

    has_full_body = (
        any(ITEM_ROLE.get(item_type_map.get(iid, "")) == "full_body" for iid in item_ids)
        and not mandatory_has_separates
    )

    for iid in item_ids:
        if iid in mandatory:
            role = ITEM_ROLE.get(item_type_map.get(iid, ""))
            if role and role != "accessory":
                seen_roles[role] = iid

    for iid in item_ids:
        is_mand = iid in mandatory
        item_type = item_type_map.get(iid, "")
        role = ITEM_ROLE.get(item_type)
        if not role:
            result.append(iid)
            continue
        if role == "accessory":
            result.append(iid)
            continue

        if not is_mand:
            if role == "full_body" and mandatory_has_separates:
                logger.warning(f"Removing {item_type} item {iid}: mandatory separates present")
                continue
            if (has_full_body or mandatory_has_full_body) and role in ("base_top", "bottom"):
                logger.warning(f"Removing {item_type} item {iid}: full_body item present")
                continue
            if role in seen_roles and seen_roles[role] != iid:
                logger.warning(
                    f"Removing duplicate {role} item {iid} ({item_type}): "
                    f"role already filled by {seen_roles[role]}"
                )
                continue

        seen_roles[role] = iid
        if iid not in result:
            result.append(iid)
    return result


_CANONICAL_ROLE_ORDER = [
    "full_body",
    "base_top",
    "mid_layer",
    "outer_layer",
    "bottom",
    "footwear",
    "socks",
    "neckwear",
    "accessory",
]

_ROLE_SORT_INDEX: dict[str, int] = {role: idx for idx, role in enumerate(_CANONICAL_ROLE_ORDER)}


def canonical_item_order(item_ids: list[UUID], item_type_map: dict[UUID, str]) -> list[UUID]:
    original_positions = {iid: idx for idx, iid in enumerate(item_ids)}

    def sort_key(item_id: UUID) -> tuple[int, int]:
        item_type = item_type_map.get(item_id, "")
        role = ITEM_ROLE.get(item_type)
        role_idx = (
            _ROLE_SORT_INDEX.get(role, len(_CANONICAL_ROLE_ORDER))
            if role
            else len(_CANONICAL_ROLE_ORDER)
        )
        return (role_idx, original_positions[item_id])

    return sorted(item_ids, key=sort_key)
