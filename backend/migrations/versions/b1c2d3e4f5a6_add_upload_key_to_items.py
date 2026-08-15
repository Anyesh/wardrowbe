"""add upload_key to clothing_items

Revision ID: b1c2d3e4f5a6
Revises: a9c8d7e6f5b4
Create Date: 2026-08-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a9c8d7e6f5b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "clothing_items", sa.Column("upload_key", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "ix_clothing_items_user_upload_key",
        "clothing_items",
        ["user_id", "upload_key"],
        unique=True,
        postgresql_where=sa.text("upload_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_clothing_items_user_upload_key", table_name="clothing_items")
    op.drop_column("clothing_items", "upload_key")
