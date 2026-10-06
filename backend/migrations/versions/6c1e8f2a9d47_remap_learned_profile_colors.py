"""remap colour names stored in learned profiles onto their vocabulary colour

Revision ID: 6c1e8f2a9d47
Revises: 952169051179
Create Date: 2026-10-05

"""

import re
from collections.abc import Iterator, Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "6c1e8f2a9d47"
down_revision: str | None = "952169051179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The same frozen colours, aliases and canonical rule as 952169051179, which remapped items and
# preferences but not the learned profiles, so scorer matches against a learned charcoal or
# "Light Blue" stopped matching gray or light-blue items.
COLORS = [
    "black",
    "white",
    "gray",
    "navy",
    "blue",
    "light-blue",
    "red",
    "burgundy",
    "pink",
    "green",
    "olive",
    "yellow",
    "orange",
    "purple",
    "brown",
    "tan",
    "beige",
    "cream",
    "gold",
    "silver",
]
COLOR_ALIASES = {
    "grey": "gray",
    "light grey": "gray",
    "light gray": "gray",
    "dark grey": "gray",
    "dark gray": "gray",
    "charcoal": "gray",
    "off-white": "cream",
    "ivory": "cream",
    "wine": "burgundy",
    "maroon": "burgundy",
    "forest green": "green",
    "army-green": "olive",
    "army green": "olive",
    "dark blue": "navy",
    "royal blue": "blue",
    "teal": "blue",
    "sky blue": "light-blue",
    "baby blue": "light-blue",
    "camel": "tan",
    "khaki": "tan",
    "dark-brown": "brown",
    "dark brown": "brown",
    "rust": "orange",
    "coral": "pink",
    "rose": "pink",
    "mauve": "purple",
    "lavender": "purple",
    "mustard": "yellow",
}

CANONICAL = {**{color: color for color in COLORS}, **COLOR_ALIASES}

BATCH_SIZE = 1000

# Zero-width space, word joiner and BOM are dropped so that a name made only of them reads as blank
# rather than as an invisible colour; ZWJ and ZWNJ stay because they shape scripts and emoji.
ZERO_WIDTH = re.compile("[\u200b\u2060\ufeff]")

WHITESPACE_RUN = re.compile(
    r"[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)


# Applied in Python rather than SQL for the reason 952169051179 gives: Postgres lower() and
# str.lower() disagree on characters such as İ and Ⓐ.
def canonical_color(name: str) -> str:
    key = WHITESPACE_RUN.sub(" ", ZERO_WIDTH.sub("", name)).strip(" ").lower()
    for candidate in (key, key.replace(" ", "-")):
        if candidate in CANONICAL:
            return CANONICAL[candidate]
    return key


# Keeps each colour at the position of its first occurrence, as 952169051179 does for arrays, and
# drops entries that are not names because the API reads preferred_colors as a list of strings.
def canonical_colors(names: list) -> list[str]:
    return list(
        dict.fromkeys(c for c in (canonical_color(n) for n in names if isinstance(n, str)) if c)
    )


# Aliases of one colour merge to the mean of their scores because the profile keeps no sample
# counts; a lone colour keeps its stored value untouched. Non-numeric scores are dropped, as
# _canonical_color_scores drops them at runtime, because every reader compares scores as numbers.
def remap_color_scores(scores):
    if not isinstance(scores, dict):
        return scores
    merged: dict[str, list[int | float]] = {}
    for name, score in scores.items():
        color = canonical_color(name)
        if color and isinstance(score, int | float) and not isinstance(score, bool):
            merged.setdefault(color, []).append(score)
    return {
        color: values[0] if len(values) == 1 else round(sum(values) / len(values), 3)
        for color, values in merged.items()
    }


def _remap_occasion(pattern):
    if isinstance(pattern, dict) and isinstance(pattern.get("preferred_colors"), list):
        return {**pattern, "preferred_colors": canonical_colors(pattern["preferred_colors"])}
    return pattern


def remap_occasion_patterns(patterns):
    if not isinstance(patterns, dict):
        return patterns
    return {occasion: _remap_occasion(pattern) for occasion, pattern in patterns.items()}


PROFILES = sa.table(
    "user_learning_profiles",
    sa.column("user_id", UUID(as_uuid=True)),
    sa.column("learned_color_scores", JSONB),
    sa.column("learned_occasion_patterns", JSONB),
)
REMAPPERS = {
    "learned_color_scores": remap_color_scores,
    "learned_occasion_patterns": remap_occasion_patterns,
}


def _batches(bind: sa.Connection) -> Iterator[list[sa.Row]]:
    after = None
    while True:
        query = sa.select(PROFILES).order_by(PROFILES.c.user_id).limit(BATCH_SIZE)
        if after is not None:
            query = query.where(PROFILES.c.user_id > after)
        rows = bind.execute(query).all()
        if not rows:
            return
        yield rows
        after = rows[-1].user_id


def upgrade() -> None:
    bind = op.get_bind()
    for rows in _batches(bind):
        for row in rows:
            changes = {}
            for column, remap in REMAPPERS.items():
                value = getattr(row, column)
                if (remapped := remap(value)) != value:
                    changes[column] = remapped
            # Only profiles whose colours change are written, so a rerun touches nothing.
            if changes:
                bind.execute(
                    sa.update(PROFILES).where(PROFILES.c.user_id == row.user_id).values(**changes)
                )


def downgrade() -> None:
    # The remap is lossy: merged scores and deduplicated colour lists keep no record of which
    # entries were aliases, so there is nothing to restore.
    pass
