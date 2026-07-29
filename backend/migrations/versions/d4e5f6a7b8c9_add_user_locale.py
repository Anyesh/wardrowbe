"""add locale to users

Persists the UI language server-side so the choice follows a user across devices
instead of living only in a browser cookie. Existing rows are backfilled to 'en'
via the server_default.

Revision ID: d4e5f6a7b8c9
Revises: c1a2b3d4e5f6
Create Date: 2026-07-29 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c1a2b3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "locale",
            sa.String(length=10),
            server_default="en",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "locale")
