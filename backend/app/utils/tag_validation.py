"""Checks for tags a client sets by hand on an item."""

from collections.abc import Mapping
from typing import Any

from app.utils.garment_vocabulary import FITS, FORMALITY, MATERIALS, PATTERNS, SEASONS, STYLES

_ONE_OF: dict[str, tuple[str, ...]] = {
    "pattern": PATTERNS,
    "material": MATERIALS,
    "formality": FORMALITY,
    "fit": FITS,
}
_MANY_OF: dict[str, tuple[str, ...]] = {
    "style": STYLES,
    "season": SEASONS,
}


def _clean(value: Any) -> str:
    return str(value).strip().lower()


def normalize_tag_edits(
    edits: dict[str, Any],
    existing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the edited tags with each closed-vocabulary value cleaned up.

    Only keys present in ``edits`` are looked at, so an item that still holds an
    older off-list value can be saved as long as that value is not being changed.
    An off-list value the item already has (``existing`` is the item's current
    tags) may also be sent back: a single value is then kept exactly as stored, and
    a style or season list may keep it beside new values, so a form that resends
    what it was shown is never blocked by data from before the vocabulary settled.
    A value is stripped and lower-cased so " Striped " is stored as "striped"; a
    null passes through because that is how a tag is cleared. Colours are not
    checked here: the colour types already canonicalise them and deliberately let
    other names through.

    Raises ValueError listing every value that is not in its vocabulary.
    """
    cleaned = dict(edits)
    problems: list[str] = []
    existing = existing or {}

    for key, allowed in _ONE_OF.items():
        value = edits.get(key)
        if value is None:
            continue
        value = _clean(value)
        if value in allowed:
            cleaned[key] = value
        elif existing.get(key) is not None and value == _clean(existing[key]):
            cleaned[key] = existing[key]
        else:
            problems.append(f"{key} {edits[key]!r} is not one of: {', '.join(allowed)}")

    for key, allowed in _MANY_OF.items():
        values = edits.get(key)
        if values is None:
            continue
        kept: list[str] = []
        already = {_clean(v) for v in (existing.get(key) or [])}
        for raw in values:
            value = _clean(raw)
            if value not in allowed and value not in already:
                problems.append(f"{key} {raw!r} is not one of: {', '.join(allowed)}")
            elif value not in kept:
                kept.append(value)
        cleaned[key] = kept

    if problems:
        raise ValueError("; ".join(problems))
    return cleaned
