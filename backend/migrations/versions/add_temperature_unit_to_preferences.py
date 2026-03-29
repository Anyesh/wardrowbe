"""add_temperature_unit_to_preferences

Revision ID: a1b2c3d4e5f6
Revises: 99f268e84ada
Create Date: 2026-03-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "99f268e84ada"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("temperature_unit", sa.String(20), nullable=True, server_default="celsius"),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "temperature_unit")
