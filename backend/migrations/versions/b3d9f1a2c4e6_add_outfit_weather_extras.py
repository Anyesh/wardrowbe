"""Add if-cooler and if-warmer items to outfits.

Two nullable foreign keys to clothing_items. The AI may name one wardrobe layer to add if it
gets cooler and one of the outfit's own layers to take off if it warms up. Deleting the item
clears the pointer instead of the outfit. Existing rows stay NULL.

Revision ID: b3d9f1a2c4e6
Revises: a7d3c9e1f5b2
Create Date: 2026-11-12 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "b3d9f1a2c4e6"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for column in ("if_cooler_item_id", "if_warmer_item_id"):
        op.add_column("outfits", sa.Column(column, UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(
            f"fk_outfits_{column}",
            "outfits",
            "clothing_items",
            [column],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    for column in ("if_warmer_item_id", "if_cooler_item_id"):
        op.drop_constraint(f"fk_outfits_{column}", "outfits", type_="foreignkey")
        op.drop_column("outfits", column)
