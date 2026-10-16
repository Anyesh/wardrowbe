"""built-in password and passkey sign-in

Revision ID: b8f1c2d3e4a5
Revises: a7d3c9e1f5b2
Create Date: 2026-10-13

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision: str = "b8f1c2d3e4a5"
down_revision: str | None = "a7d3c9e1f5b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive only: existing accounts keep their identities and data, and get a password later
    # through /setup (empty install) or `python -m app.cli set-password`.
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    op.drop_constraint("ck_user_identities_provider", "user_identities", type_="check")
    op.create_check_constraint(
        "ck_user_identities_provider",
        "user_identities",
        "provider IN ('legacy', 'dev', 'oidc', 'forward_auth', 'local')",
    )

    op.create_table(
        "webauthn_credentials",
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
        sa.Column("credential_id", sa.LargeBinary(), nullable=False),
        sa.Column("public_key", sa.LargeBinary(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "transports", ARRAY(sa.String(32)), nullable=False, server_default=sa.text("'{}'")
        ),
        sa.Column("backed_up", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("credential_id", name="uq_webauthn_credentials_credential_id"),
    )
    op.create_index("ix_webauthn_credentials_user_id", "webauthn_credentials", ["user_id"])


def downgrade() -> None:
    # Lossy: passwords and passkeys are dropped, and so are the local identities, which ends
    # every session they minted. Accounts and their wardrobes stay.
    op.drop_index("ix_webauthn_credentials_user_id", table_name="webauthn_credentials")
    op.drop_table("webauthn_credentials")
    op.execute("DELETE FROM user_identities WHERE provider = 'local'")
    op.drop_constraint("ck_user_identities_provider", "user_identities", type_="check")
    op.create_check_constraint(
        "ck_user_identities_provider",
        "user_identities",
        "provider IN ('legacy', 'dev', 'oidc', 'forward_auth')",
    )
    op.drop_column("users", "is_admin")
    op.drop_column("users", "password_hash")
