"""clear the English name stored on wore-instead outfits

Revision ID: a7d3c9e1f5b2
Revises: 6c1e8f2a9d47
Create Date: 2026-10-06

"""

from collections.abc import Sequence

from alembic import op

revision: str = "a7d3c9e1f5b2"
down_revision: str | None = "6c1e8f2a9d47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE outfits
        SET name = NULL
        WHERE replaces_outfit_id IS NOT NULL
          AND name = initcap(COALESCE(occasion, 'Outfit')) || ' (wore instead)'
        """
    )


def downgrade() -> None:
    # The generated English names are not restored: the UI renders a translated title instead.
    pass
