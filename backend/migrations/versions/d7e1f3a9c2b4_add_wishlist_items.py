"""wishlist: things to buy, with a photo, notes, link and price

Revision ID: d7e1f3a9c2b4
Revises: c4d9e2a7b1f3
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d7e1f3a9c2b4"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wishlist_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("link", sa.String(1000), nullable=True),
        sa.Column("image_url", sa.String(1000), nullable=True),
        sa.Column("image_path", sa.String(500), nullable=True),
        sa.Column("thumbnail_path", sa.String(500), nullable=True),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("item_type", sa.String(50), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("bought", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_wishlist_items_user_id", "wishlist_items", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_wishlist_items_user_id", table_name="wishlist_items")
    op.drop_table("wishlist_items")
