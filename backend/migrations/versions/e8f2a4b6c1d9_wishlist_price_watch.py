"""wishlist price watch: latest shop price, last check and last drop

Revision ID: e8f2a4b6c1d9
Revises: d7e1f3a9c2b4
Create Date: 2026-10-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e8f2a4b6c1d9"
down_revision: str | None = "d7e1f3a9c2b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wishlist_items", sa.Column("current_price", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "wishlist_items", sa.Column("price_checked_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "wishlist_items", sa.Column("price_dropped_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("wishlist_items", "price_dropped_at")
    op.drop_column("wishlist_items", "price_checked_at")
    op.drop_column("wishlist_items", "current_price")
