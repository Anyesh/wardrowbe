"""remap colour names stored in learned profiles onto their vocabulary colour

Revision ID: 6c1e8f2a9d47
Revises: 952169051179
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6c1e8f2a9d47"
down_revision: str | None = "952169051179"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The same frozen alias table as 952169051179, which remapped items and preferences but not the
# learned profiles, so scorer matches against a learned charcoal stopped matching gray items.
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

# Aliases of one colour merge to the mean of their scores because the profile keeps no sample
# counts; a lone colour keeps its stored value untouched. Rows holding any non-numeric score are
# skipped rather than guessed at.
REMAP_COLOR_SCORES = f"""
WITH {ALIAS_CTE},
remapped AS (
    SELECT p.user_id, (
        SELECT jsonb_object_agg(s.color, s.score) FROM (
            SELECT
                COALESCE(a.target, e.key) AS color,
                CASE WHEN count(*) = 1 THEN (array_agg(e.value))[1]
                    ELSE to_jsonb(round(avg(CAST(e.value AS numeric)), 3))
                END AS score
            FROM jsonb_each(p.learned_color_scores) e
            LEFT JOIN alias a ON a.name = lower(btrim(e.key))
            GROUP BY 1
        ) s
    ) AS scores
    FROM user_learning_profiles p
    WHERE jsonb_typeof(p.learned_color_scores) = 'object'
        AND p.learned_color_scores <> '{{}}'::jsonb
        AND NOT EXISTS (
            SELECT 1 FROM jsonb_each(p.learned_color_scores) e
            WHERE jsonb_typeof(e.value) <> 'number'
        )
)
UPDATE user_learning_profiles p SET learned_color_scores = r.scores
FROM remapped r
WHERE p.user_id = r.user_id AND p.learned_color_scores IS DISTINCT FROM r.scores
"""

# Keeps each colour at the position of its first occurrence, as 952169051179 does for arrays.
REMAP_OCCASION_COLORS = f"""
WITH {ALIAS_CTE},
remapped AS (
    SELECT p.user_id, (
        SELECT jsonb_object_agg(
            o.key,
            CASE WHEN jsonb_typeof(o.value -> 'preferred_colors') = 'array' THEN
                jsonb_set(o.value, '{{preferred_colors}}', COALESCE((
                    SELECT jsonb_agg(s.color ORDER BY s.first) FROM (
                        SELECT COALESCE(a.target, c.value) AS color, min(c.position) AS first
                        FROM jsonb_array_elements_text(o.value -> 'preferred_colors')
                            WITH ORDINALITY AS c(value, position)
                        LEFT JOIN alias a ON a.name = lower(btrim(c.value))
                        GROUP BY 1
                    ) s
                ), '[]'::jsonb))
            ELSE o.value END
        )
        FROM jsonb_each(p.learned_occasion_patterns) o
    ) AS patterns
    FROM user_learning_profiles p
    WHERE jsonb_typeof(p.learned_occasion_patterns) = 'object'
        AND p.learned_occasion_patterns <> '{{}}'::jsonb
)
UPDATE user_learning_profiles p SET learned_occasion_patterns = r.patterns
FROM remapped r
WHERE p.user_id = r.user_id AND p.learned_occasion_patterns IS DISTINCT FROM r.patterns
"""


def upgrade() -> None:
    bind = op.get_bind()
    params = {"names": list(COLOR_ALIASES), "targets": list(COLOR_ALIASES.values())}
    bind.execute(sa.text(REMAP_COLOR_SCORES), params)
    bind.execute(sa.text(REMAP_OCCASION_COLORS), params)


def downgrade() -> None:
    # The remap is lossy: merged scores and deduplicated colour lists keep no record of which
    # entries were aliases, so there is nothing to restore.
    pass
