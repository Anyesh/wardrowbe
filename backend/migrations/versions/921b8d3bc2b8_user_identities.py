"""one sign-in identity per provider in user_identities

Revision ID: 921b8d3bc2b8
Revises: 6c1e8f2a9d47
Create Date: 2026-10-06

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "921b8d3bc2b8"
down_revision: str | None = "6c1e8f2a9d47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Taken before anything else so that a running backend cannot commit a user between the
    # backfill's snapshot and the ALTER, and so that no lock upgrade can deadlock a sign-in.
    op.execute("LOCK TABLE users IN ACCESS EXCLUSIVE MODE")
    op.create_table(
        "user_identities",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('legacy', 'dev', 'oidc', 'forward_auth')",
            name="ck_user_identities_provider",
        ),
        sa.UniqueConstraint("provider", "subject", name="uq_user_identities_provider_subject"),
        sa.UniqueConstraint("user_id", "provider", name="uq_user_identities_user_provider"),
    )
    op.execute(
        """
        INSERT INTO user_identities (id, user_id, provider, subject, created_at)
        SELECT gen_random_uuid(), id, 'legacy', external_id, created_at FROM users
        """
    )
    op.alter_column("users", "external_id", existing_type=sa.String(255), nullable=True)


def downgrade() -> None:
    # Lossy by design but never fails: each user gets its best subject (oidc, then dev, then
    # legacy, then a still-set external_id of a user without identities), a subject held by
    # several users goes to the best-ranked one, and everyone else gets a unique placeholder.
    # forward_auth subjects are never candidates, so a proxy username cannot land an OIDC
    # subject's sign-in in the proxy user's account. The trigger is disabled so that the rewrite
    # does not bump every user's updated_at.
    op.execute("LOCK TABLE users, user_identities IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE users DISABLE TRIGGER update_users_updated_at")
    op.execute(
        """
        CREATE TEMP TABLE identity_downgrade ON COMMIT DROP AS
        WITH candidates AS (
            SELECT user_id, subject,
                   CASE provider WHEN 'oidc' THEN 1 WHEN 'dev' THEN 2 ELSE 3 END AS rank
            FROM user_identities
            WHERE provider IN ('oidc', 'dev', 'legacy')
            UNION ALL
            SELECT u.id, u.external_id, 4
            FROM users u
            WHERE u.external_id IS NOT NULL
              AND NOT EXISTS (SELECT 1 FROM user_identities i WHERE i.user_id = u.id)
        ),
        best AS (
            SELECT DISTINCT ON (user_id) user_id, subject, rank
            FROM candidates
            ORDER BY user_id, rank
        ),
        winners AS (
            SELECT user_id, subject,
                   row_number() OVER (PARTITION BY subject ORDER BY rank, user_id) AS position
            FROM best
        )
        SELECT u.id AS user_id,
               COALESCE(w.subject, 'downgraded:' || u.id || ':' || gen_random_uuid())
                   AS external_id
        FROM users u
        LEFT JOIN winners w ON w.user_id = u.id AND w.position = 1
        """
    )
    # Two statements because Postgres checks a non-deferrable UNIQUE row by row, so moving a
    # subject from one user to another in a single UPDATE can collide midway.
    op.execute("UPDATE users SET external_id = NULL")
    op.execute(
        """
        UPDATE users u SET external_id = d.external_id
        FROM identity_downgrade d
        WHERE d.user_id = u.id
        """
    )
    op.execute("DROP TABLE identity_downgrade")
    op.alter_column("users", "external_id", existing_type=sa.String(255), nullable=False)
    op.drop_table("user_identities")
    op.execute("ALTER TABLE users ENABLE TRIGGER update_users_updated_at")
