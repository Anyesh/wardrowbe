"""item images: own background-removal state and original backup per photo

Revision ID: a4c6e8f0b2d3
Revises: f3b5c7d9e1a2
Create Date: 2026-10-18

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4c6e8f0b2d3"
down_revision: str | None = "f3b5c7d9e1a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive: every existing photo reads as ready with no backup, which is what it is.
    op.add_column(
        "item_images",
        sa.Column("status", sa.String(12), nullable=False, server_default="ready"),
    )
    op.add_column("item_images", sa.Column("original_image_path", sa.String(500), nullable=True))
    op.add_column(
        "item_images",
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_item_images_status", "item_images", "status IN ('ready', 'processing', 'error')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_item_images_status", "item_images", type_="check")
    op.drop_column("item_images", "processing_started_at")
    op.drop_column("item_images", "original_image_path")
    op.drop_column("item_images", "status")
