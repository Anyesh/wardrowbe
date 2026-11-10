"""declutter review: items kept until a date stay out of the review

Revision ID: c4d9e2a7b1f3
Revises: b8f1c2d3e4a5
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c4d9e2a7b1f3"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "declutter_keeps",
        sa.Column(
            "item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clothing_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("kept_until", sa.Date(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("declutter_keeps")
