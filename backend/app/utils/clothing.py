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
    requested = mandatory_item_ids or set()
    result: list[UUID] = []

    # A mandatory item only claims a slot if the caller actually passed it in item_ids;
    # one that never made the candidate list must not block the items that did.
    # Mandatory items compete with each other too, first in list order wins, because two
    # shirts or a dress plus trousers is an unwearable outfit however it was requested.
    mandatory_roles: dict[str, UUID] = {}
    body_claim: str | None = None
    for iid in item_ids:
        if iid not in requested:
            continue
        role = ITEM_ROLE.get(item_type_map.get(iid, ""))
        if not role or role == "accessory" or role in mandatory_roles:
            continue
        if role == "full_body":
            if body_claim == "separates":
                continue
            body_claim = "full_body"
        elif role in ("base_top", "bottom"):
            if body_claim == "full_body":
                continue
            body_claim = "separates"
        mandatory_roles[role] = iid

    mandatory_has_separates = body_claim == "separates"
    has_full_body = body_claim == "full_body" or (
        not mandatory_has_separates
        and any(ITEM_ROLE.get(item_type_map.get(iid, "")) == "full_body" for iid in item_ids)
    )

    seen_roles: dict[str, UUID] = dict(mandatory_roles)
    for iid in item_ids:
        item_type = item_type_map.get(iid, "")
        role = ITEM_ROLE.get(item_type)
        if not role or role == "accessory":
            result.append(iid)
            continue
        if mandatory_roles.get(role) == iid:
            result.append(iid)
            continue
        if role == "full_body" and mandatory_has_separates:
            logger.warning(f"Removing {item_type} item {iid}: mandatory separates present")
            continue
        if has_full_body and role in ("base_top", "bottom"):
            logger.warning(f"Removing {item_type} item {iid}: full_body item present")
            continue
        if role in seen_roles:
            logger.warning(
                f"Removing duplicate {role} item {iid} ({item_type}): "
                f"role already filled by {seen_roles[role]}"
            )
            continue
        seen_roles[role] = iid
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
