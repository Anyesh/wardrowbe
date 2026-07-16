"""add_original_image_path_to_items

Revision ID: b8c9d0e1f2a3
Revises: f2a3b4c5d6e7
Create Date: 2026-07-16

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: str | None = "f2a3b4c5d6e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("original_image_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("clothing_items", "original_image_path")
