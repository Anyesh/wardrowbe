"""item photo views: which photo of an item shows the front, the back or a detail

Revision ID: f3b5c7d9e1a2
Revises: a7d3c9e1f5b2
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3b5c7d9e1a2"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: existing photos simply have no view until the user labels them.
    op.create_table(
        "item_photo_views",
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clothing_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("image_path", sa.String(500), primary_key=True),
        sa.Column("view", sa.String(10), nullable=False),
        sa.CheckConstraint(
            "view IN ('front', 'back', 'detail', 'other')", name="ck_item_photo_views_view"
        ),
    )


def downgrade() -> None:
    op.drop_table("item_photo_views")
