"""add ai_completed_at to clothing_items

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-04

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: str | None = "c4d5e6f7a8b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items", sa.Column("ai_completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_clothing_items_user_ai_completed_at",
        "clothing_items",
        ["user_id", "ai_completed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_clothing_items_user_ai_completed_at", table_name="clothing_items")
    op.drop_column("clothing_items", "ai_completed_at")
