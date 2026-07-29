"""add_ai_job_id_to_items

Revision ID: f2a3b4c5d6e7
Revises: e1f2g3h4i5j6
Create Date: 2026-07-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: str | None = "e1f2g3h4i5j6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clothing_items", sa.Column("ai_job_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("clothing_items", "ai_job_id")
