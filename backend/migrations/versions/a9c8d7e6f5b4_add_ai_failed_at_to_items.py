"""add ai_failed_at to clothing_items

Revision ID: a9c8d7e6f5b4
Revises: f3b4c5d6e7a8
Create Date: 2026-08-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9c8d7e6f5b4"
down_revision: str | None = "f3b4c5d6e7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items", sa.Column("ai_failed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("clothing_items", "ai_failed_at")
