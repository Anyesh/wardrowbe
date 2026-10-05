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

# A frozen copy of garment_vocabulary.json's color_aliases at this revision, because a migration
# must keep doing what it did when it shipped even after the vocabulary changes. The old colour
# picker offered charcoal, khaki, teal, army-green and dark-brown, which the tagger never stored.
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

ALIAS_CTE = "alias(name, target) AS (SELECT * FROM unnest(CAST(:names AS text[]), CAST(:targets AS text[])))"

ARRAY_COLUMNS = [
    ("clothing_items", "id", "colors"),
    ("user_preferences", "user_id", "color_favorites"),
    ("user_preferences", "user_id", "color_avoid"),
]


def _remap_array(table: str, key: str, column: str) -> sa.TextClause:
    # Keeps each colour at the position of its first occurrence, so the order the user or tagger
    # chose survives while charcoal + gray collapse into one gray.
    return sa.text(
        f"""
        WITH {ALIAS_CTE},
        remapped AS (
            SELECT t.{key} AS key, ARRAY(
                SELECT s.color FROM (
                    SELECT COALESCE(a.target, u.value) AS color, min(u.position) AS first
                    FROM unnest(t.{column}) WITH ORDINALITY AS u(value, position)
                    LEFT JOIN alias a ON a.name = lower(btrim(u.value))
                    GROUP BY 1
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
    params = {"names": list(COLOR_ALIASES), "targets": list(COLOR_ALIASES.values())}
    bind.execute(
        sa.text(
            f"""
            WITH {ALIAS_CTE}
            UPDATE clothing_items t SET primary_color = a.target
            FROM alias a
            WHERE lower(btrim(t.primary_color)) = a.name
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
