"""Add optional item size, purchase store, and care instructions.

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6f7a8b9c0d1"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("size", sa.String(length=50), nullable=True))
    op.add_column(
        "clothing_items", sa.Column("purchase_store", sa.String(length=100), nullable=True)
    )
    op.add_column("clothing_items", sa.Column("care_instructions", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("clothing_items", "care_instructions")
    op.drop_column("clothing_items", "purchase_store")
    op.drop_column("clothing_items", "size")
