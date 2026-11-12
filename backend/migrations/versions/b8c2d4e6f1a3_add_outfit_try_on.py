"""Add outfit try-on: the user's reference photo and one generated image per outfit.

Revision ID: b8c2d4e6f1a3
Revises: a7d3c9e1f5b2
Create Date: 2026-11-12 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b8c2d4e6f1a3"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

try_on_status = postgresql.ENUM(
    "pending", "ready", "failed", name="try_on_status", create_type=False
)


def upgrade() -> None:
    op.create_table(
        "try_on_photos",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=False),
        sa.Column("medium_path", sa.String(length=500), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    try_on_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "outfit_try_ons",
        sa.Column("outfit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", try_on_status, nullable=False),
        sa.Column("error_code", sa.String(length=50), nullable=True),
        sa.Column("cache_key", sa.String(length=64), nullable=False),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("medium_path", sa.String(length=500), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["outfit_id"], ["outfits.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("outfit_id"),
    )
    op.create_index("ix_outfit_try_ons_user_id", "outfit_try_ons", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_outfit_try_ons_user_id", table_name="outfit_try_ons")
    op.drop_table("outfit_try_ons")
    try_on_status.drop(op.get_bind(), checkfirst=True)
    op.drop_table("try_on_photos")
