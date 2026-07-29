"""add_item_tagging_status

Adds an explicit tagging lifecycle to clothing items so an external agent can own
tagging when internal vision is disabled. New native PG enums tagging_status
(pending|tagged) and tagged_by (auto|manual), plus tagging_status / tagged_by /
tagged_at columns on clothing_items. Existing rows are backfilled to tagged/auto so
they never surface in the agent's pending work-queue (back-compat: behavior unchanged).

Revision ID: c1a2b3d4e5f6
Revises: b8c9d0e1f2a3
Create Date: 2026-06-19 18:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1a2b3d4e5f6"
down_revision: str | None = "b8c9d0e1f2a3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE tagging_status AS ENUM ('pending', 'tagged')")
    op.execute("CREATE TYPE tagged_by AS ENUM ('auto', 'manual')")

    op.add_column(
        "clothing_items",
        sa.Column(
            "tagging_status",
            postgresql.ENUM("pending", "tagged", name="tagging_status", create_type=False),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "clothing_items",
        sa.Column(
            "tagged_by",
            postgresql.ENUM("auto", "manual", name="tagged_by", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "clothing_items",
        sa.Column("tagged_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Back-compat: existing items predate external tagging and were tagged by the
    # internal AI. Mark them tagged/auto so they don't appear as pending agent work.
    op.execute(
        "UPDATE clothing_items "
        "SET tagging_status = 'tagged', tagged_by = 'auto', "
        "tagged_at = COALESCE(updated_at, now())"
    )


def downgrade() -> None:
    op.drop_column("clothing_items", "tagged_at")
    op.drop_column("clothing_items", "tagged_by")
    op.drop_column("clothing_items", "tagging_status")
    op.execute("DROP TYPE IF EXISTS tagged_by")
    op.execute("DROP TYPE IF EXISTS tagging_status")
