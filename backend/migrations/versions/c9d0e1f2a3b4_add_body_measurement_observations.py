"""add time-aware body measurement observations

Revision ID: c9d0e1f2a3b4
Revises: d5e6f7a8b9c0
Create Date: 2026-09-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d0e1f2a3b4"
down_revision: str | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "body_measurement_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("value", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit", sa.String(length=16), nullable=False),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_body_measurement_observations_user_id",
        "body_measurement_observations",
        ["user_id"],
    )
    op.create_index(
        "ix_body_measurement_observations_metric",
        "body_measurement_observations",
        ["metric"],
    )

    op.execute(
        sa.text(
            """
            INSERT INTO body_measurement_observations
                (id, user_id, metric, value, unit, measured_at, source, created_at)
            SELECT
                gen_random_uuid(),
                users.id,
                entry.key,
                (entry.value #>> '{}')::numeric,
                CASE WHEN entry.key = 'weight' THEN 'kg' ELSE 'cm' END,
                NULL,
                'legacy_profile',
                now()
            FROM users
            CROSS JOIN LATERAL jsonb_each(users.body_measurements) AS entry(key, value)
            WHERE users.body_measurements IS NOT NULL
              AND entry.key IN ('weight', 'chest', 'waist', 'hips', 'inseam', 'height')
              AND jsonb_typeof(entry.value) = 'number'
              AND (entry.value #>> '{}')::numeric > 0
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_body_measurement_observations_metric",
        table_name="body_measurement_observations",
    )
    op.drop_index(
        "ix_body_measurement_observations_user_id",
        table_name="body_measurement_observations",
    )
    op.drop_table("body_measurement_observations")
