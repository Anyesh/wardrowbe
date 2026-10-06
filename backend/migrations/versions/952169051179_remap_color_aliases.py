"""remap colour names that are not stored colours onto their vocabulary colour

Revision ID: 952169051179
Revises: b7e2c9a41f36
Create Date: 2026-10-05

"""

import re
from collections.abc import Iterator, Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "952169051179"
down_revision: str | None = "b7e2c9a41f36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Frozen copies of garment_vocabulary.json's colors and color_aliases at this revision, because a
# migration must keep doing what it did when it shipped even after the vocabulary changes. The old
# colour picker offered charcoal, khaki, teal, army-green and dark-brown, which the tagger never
# stored, and API clients wrote names such as "Navy" or "Light Blue" as typed.
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

# Every stored colour maps to itself so that a cased or spaced spelling of it resolves as well.
CANONICAL = {**{color: color for color in COLORS}, **COLOR_ALIASES}

BATCH_SIZE = 1000

# Unicode White_Space spelled out rather than \s, as normalize_color spells it.
WHITESPACE_RUN = re.compile(
    r"[\t\n\v\f\r \u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+"
)


# canonical_color at this revision, applied in Python rather than SQL because Postgres lower()
# disagrees with str.lower() on characters such as İ and Ⓐ, and lowercases only ASCII on a
# C-collation database, so unknown names would be stored differently from runtime writes.
def canonical_color(name: str) -> str:
    key = WHITESPACE_RUN.sub(" ", name).strip(" ").lower()
    for candidate in (key, key.replace(" ", "-")):
        if candidate in CANONICAL:
            return CANONICAL[candidate]
    return key


# Keeps each colour at the position of its first occurrence, so the order the user or tagger chose
# survives while charcoal + gray collapse into one gray. NULL and blank entries are dropped because
# no colour filter or swatch can use them.
def canonical_colors(names: list[str | None]) -> list[str]:
    return list(dict.fromkeys(c for c in (canonical_color(n) for n in names if n is not None) if c))


# A blank primary colour becomes NULL, as the item schemas store it.
def canonical_primary_color(name: str) -> str | None:
    return canonical_color(name) or None


ITEMS = sa.table(
    "clothing_items",
    sa.column("id", UUID(as_uuid=True)),
    sa.column("primary_color", sa.String),
    sa.column("colors", ARRAY(sa.String)),
)
PREFERENCES = sa.table(
    "user_preferences",
    sa.column("user_id", UUID(as_uuid=True)),
    sa.column("color_favorites", ARRAY(sa.String)),
    sa.column("color_avoid", ARRAY(sa.String)),
)


def _batches(bind: sa.Connection, table: sa.TableClause, key: str) -> Iterator[list[sa.Row]]:
    after = None
    while True:
        query = sa.select(table).order_by(table.c[key]).limit(BATCH_SIZE)
        if after is not None:
            query = query.where(table.c[key] > after)
        rows = bind.execute(query).all()
        if not rows:
            return
        yield rows
        after = getattr(rows[-1], key)


def _remap(bind: sa.Connection, table: sa.TableClause, key: str, remappers: dict) -> None:
    for rows in _batches(bind, table, key):
        for row in rows:
            changes = {}
            for column, remap in remappers.items():
                value = getattr(row, column)
                if value is not None and (remapped := remap(value)) != value:
                    changes[column] = remapped
            # Only rows whose colours change are written, so a rerun touches nothing.
            if changes:
                bind.execute(
                    sa.update(table).where(table.c[key] == getattr(row, key)).values(**changes)
                )


def upgrade() -> None:
    bind = op.get_bind()
    _remap(
        bind,
        ITEMS,
        "id",
        {"primary_color": canonical_primary_color, "colors": canonical_colors},
    )
    _remap(
        bind,
        PREFERENCES,
        "user_id",
        {"color_favorites": canonical_colors, "color_avoid": canonical_colors},
    )


def downgrade() -> None:
    # The remap is lossy: once charcoal became gray there is no record of which grays were
    # charcoal, so there is nothing to restore.
    pass
