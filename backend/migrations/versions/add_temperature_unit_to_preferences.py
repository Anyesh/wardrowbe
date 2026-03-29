"""add_temperature_unit_to_preferences

Revision ID: 2bc743c6eefd
Revises: a7b8c9d0e1f2
Create Date: 2026-03-29 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "2bc743c6eefd"
down_revision: str | None = "a7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("temperature_unit", sa.String(20), nullable=True, server_default="celsius"),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "temperature_unit")
