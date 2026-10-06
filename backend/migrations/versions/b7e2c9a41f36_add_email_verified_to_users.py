"""add email_verified to users

Revision ID: b7e2c9a41f36
Revises: d5e6f7a8b9c0
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7e2c9a41f36"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Existing accounts are backfilled as verified so that provider migrations keep working
    # for them; rows inserted afterwards are unverified unless the sync says otherwise.
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("users", "email_verified", server_default=sa.false())


def downgrade() -> None:
    op.drop_column("users", "email_verified")
