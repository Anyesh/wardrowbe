"""Checks for tags a client sets by hand on an item."""

from typing import Any

from app.utils.garment_vocabulary import FITS, FORMALITY, PATTERNS, SEASONS, STYLES

# The tags the scorer and the recommendation prompts compare against these lists. Material is
# not here: it is shown as written (clients send things like "100% linen"), so it stays free text.
_ONE_OF: dict[str, tuple[str, ...]] = {
    "pattern": PATTERNS,
    "formality": FORMALITY,
    "fit": FITS,
}
_MANY_OF: dict[str, tuple[str, ...]] = {
    "style": STYLES,
    "season": SEASONS,
}


def _clean(value: Any) -> str:
    return str(value).strip().lower()


def normalize_tag_edits(edits: dict[str, Any]) -> dict[str, Any]:
    """Return the edited tags with each closed-vocabulary value cleaned up.

    Only keys present in ``edits`` are looked at, so an item that still holds an
    older off-list value can be saved as long as that value is not being changed.
    A value is stripped and lower-cased so " Striped " is stored as "striped"; a
    null passes through because that is how a tag is cleared. Colours and
    material are not checked here: the colour types already canonicalise colours
    and deliberately let other names through, and material is free text.

    Raises ValueError listing every value that is not in its vocabulary.
    """
    cleaned = dict(edits)
    problems: list[str] = []

    for key, allowed in _ONE_OF.items():
        value = edits.get(key)
        if value is None:
            continue
        value = _clean(value)
        if value in allowed:
            cleaned[key] = value
        else:
            problems.append(f"{key} {edits[key]!r} is not one of: {', '.join(allowed)}")

    for key, allowed in _MANY_OF.items():
        values = edits.get(key)
        if values is None:
            continue
        kept: list[str] = []
        for raw in values:
            value = _clean(raw)
            if value not in allowed:
                problems.append(f"{key} {raw!r} is not one of: {', '.join(allowed)}")
            elif value not in kept:
                kept.append(value)
        cleaned[key] = kept

    if problems:
        raise ValueError("; ".join(problems))
    return cleaned
