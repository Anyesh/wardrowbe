from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "45702c628c1f"
down_revision: str | None = "c3d4e5f6a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("schedules_user_id_day_of_week_key", "schedules", type_="unique")


def downgrade() -> None:
    op.create_unique_constraint(
        "schedules_user_id_day_of_week_key", "schedules", ["user_id", "day_of_week"]
    )
