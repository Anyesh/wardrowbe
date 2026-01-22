"""add wore_instead tracking fields

Revision ID: 9a4d3f6e8c12
Revises: 8f3c2d5e7b91
Create Date: 2026-01-21 23:00:00.000000

This migration adds fields to track what users actually wore when they
didn't follow a recommendation, enabling better learning of user preferences.

Fields added to user_feedback:
- actually_worn: Boolean indicating if user wore the recommended outfit
- wore_instead_items: JSONB array of item UUIDs user wore instead

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "9a4d3f6e8c12"
down_revision: str | None = "8f3c2d5e7b91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add actually_worn column
    op.add_column("user_feedback", sa.Column("actually_worn", sa.Boolean, nullable=True))

    # Add wore_instead_items column (JSONB array of item UUIDs)
    op.add_column("user_feedback", sa.Column("wore_instead_items", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("user_feedback", "wore_instead_items")
    op.drop_column("user_feedback", "actually_worn")
