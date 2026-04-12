"""Add outfit studio schema: name, replaces, cloned_from, nullable scheduled_for, skipped status, wear_bonus, indexes.

Revision ID: 7a3b5c8d9e0f
Revises: 2bc743c6eefd
Create Date: 2026-04-12
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "7a3b5c8d9e0f"
down_revision: str | None = "2bc743c6eefd"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE outfit_status ADD VALUE IF NOT EXISTS 'skipped'")

    op.add_column("outfits", sa.Column("name", sa.String(100), nullable=True))
    op.add_column(
        "outfits",
        sa.Column(
            "replaces_outfit_id",
            UUID(as_uuid=True),
            sa.ForeignKey("outfits.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "outfits",
        sa.Column(
            "cloned_from_outfit_id",
            UUID(as_uuid=True),
            sa.ForeignKey("outfits.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    op.alter_column("outfits", "scheduled_for", existing_type=sa.Date(), nullable=True)

    op.add_column(
        "item_pair_scores",
        sa.Column("wear_bonus", sa.Numeric(5, 4), server_default="0", nullable=True),
    )

    op.create_index(
        "ix_outfits_user_source",
        "outfits",
        ["user_id", "source"],
    )
    op.create_index(
        "ix_outfits_user_lookbook",
        "outfits",
        ["user_id"],
        postgresql_where=sa.text("scheduled_for IS NULL"),
    )
    op.create_index(
        "ix_outfits_cloned_from",
        "outfits",
        ["cloned_from_outfit_id"],
        postgresql_where=sa.text("cloned_from_outfit_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_outfits_cloned_from", table_name="outfits")
    op.drop_index("ix_outfits_user_lookbook", table_name="outfits")
    op.drop_index("ix_outfits_user_source", table_name="outfits")

    op.drop_column("item_pair_scores", "wear_bonus")

    op.alter_column("outfits", "scheduled_for", existing_type=sa.Date(), nullable=False)

    op.drop_column("outfits", "cloned_from_outfit_id")
    op.drop_column("outfits", "replaces_outfit_id")
    op.drop_column("outfits", "name")
