"""remap colour names that are not stored colours onto their vocabulary colour

Revision ID: 952169051179
Revises: b7e2c9a41f36
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

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

CANONICAL_CTE = (
    "canonical(name, target) AS "
    "(SELECT * FROM unnest(CAST(:names AS text[]), CAST(:targets AS text[])))"
)

ARRAY_COLUMNS = [
    ("clothing_items", "id", "colors"),
    ("user_preferences", "user_id", "color_favorites"),
    ("user_preferences", "user_id", "color_avoid"),
]


# The SQL form of normalize_color at this revision: trim and lowercase, try the name as written and
# with its whitespace collapsed to one hyphen, and keep an unknown name in its trimmed lowercase.
def canonical_color_sql(value: str) -> str:
    key = f"lower(btrim({value}))"
    return f"""COALESCE(
        (SELECT canon.target FROM canonical canon WHERE canon.name = {key}),
        (SELECT canon.target FROM canonical canon
            WHERE canon.name = regexp_replace({key}, '\\s+', '-', 'g')),
        {key}
    )"""


def _remap_array(table: str, key: str, column: str) -> sa.TextClause:
    # Keeps each colour at the position of its first occurrence, so the order the user or tagger
    # chose survives while charcoal + gray collapse into one gray. NULL and blank entries are
    # dropped because no colour filter or swatch can use them.
    return sa.text(
        f"""
        WITH {CANONICAL_CTE},
        remapped AS (
            SELECT t.{key} AS key, ARRAY(
                SELECT s.color FROM (
                    SELECT e.color, min(e.position) AS first
                    FROM (
                        SELECT {canonical_color_sql("u.value")} AS color, u.position
                        FROM unnest(t.{column}) WITH ORDINALITY AS u(value, position)
                        WHERE btrim(u.value) <> ''
                    ) e
                    GROUP BY e.color
                ) s
                ORDER BY s.first
            ) AS colors
            FROM {table} t
            WHERE t.{column} IS NOT NULL
        )
        UPDATE {table} t SET {column} = r.colors
        FROM remapped r
        WHERE t.{key} = r.key AND CAST(t.{column} AS text[]) IS DISTINCT FROM r.colors
        """
    )


def upgrade() -> None:
    bind = op.get_bind()
    params = {"names": list(CANONICAL), "targets": list(CANONICAL.values())}
    canonical_primary = canonical_color_sql("t.primary_color")
    bind.execute(
        sa.text(
            f"""
            WITH {CANONICAL_CTE}
            UPDATE clothing_items t SET primary_color = {canonical_primary}
            WHERE btrim(t.primary_color) <> ''
                AND t.primary_color IS DISTINCT FROM {canonical_primary}
            """
        ),
        params,
    )
    for table, key, column in ARRAY_COLUMNS:
        bind.execute(_remap_array(table, key, column), params)


def downgrade() -> None:
    # The remap is lossy: once charcoal became gray there is no record of which grays were
    # charcoal, so there is nothing to restore.
    pass
