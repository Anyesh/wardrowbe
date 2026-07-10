"""Add the external outfit source and authoring attribute columns.

'external' names the write path: outfits authored through the external
authoring API rather than generated internally, composed in the studio, or
derived from a pairing request. The backend can attest to the write path, so
the value carries the same server-derived semantics as the tagging origins.

The four attribute columns (season, formality, palette, notes) let an author
record the outfit qualities the internal AI keeps implicit in its reasoning.
All nullable; existing rows and the internal generation paths are unaffected.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-10 17:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE outfit_source ADD VALUE IF NOT EXISTS 'external'")

    op.add_column("outfits", sa.Column("season", sa.String(length=20), nullable=True))
    op.add_column("outfits", sa.Column("formality", sa.String(length=50), nullable=True))
    op.add_column("outfits", sa.Column("palette", JSONB, nullable=True))
    op.add_column("outfits", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("outfits", "notes")
    op.drop_column("outfits", "palette")
    op.drop_column("outfits", "formality")
    op.drop_column("outfits", "season")

    # Note: Cannot remove enum value in PostgreSQL, so 'external' will remain
