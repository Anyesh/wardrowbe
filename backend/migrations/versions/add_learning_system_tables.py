"""add_learning_system_tables

Revision ID: 8f3c2d5e7b91
Revises: 17e405de9371
Create Date: 2026-01-21 12:00:00.000000

This migration adds tables for the continuous AI learning system that learns
from user feedback to improve recommendations, similar to Netflix/Spotify.

Tables added:
- user_learning_profiles: Stores computed learning insights per user
- item_pair_scores: Tracks which item combinations work well together
- outfit_performances: Stores performance metrics for outfits
- style_insights: Human-readable insights about user preferences

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "8f3c2d5e7b91"
down_revision: str | None = "17e405de9371"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create user_learning_profiles table
    op.create_table(
        "user_learning_profiles",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("learned_color_scores", JSONB, nullable=False, server_default="{}"),
        sa.Column("learned_style_scores", JSONB, nullable=False, server_default="{}"),
        sa.Column("learned_occasion_patterns", JSONB, nullable=False, server_default="{}"),
        sa.Column("learned_weather_preferences", JSONB, nullable=False, server_default="{}"),
        sa.Column("learned_temporal_patterns", JSONB, nullable=False, server_default="{}"),
        sa.Column("overall_acceptance_rate", sa.Numeric(5, 4), nullable=True),
        sa.Column("average_overall_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("average_comfort_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("average_style_rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("feedback_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("outfits_rated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_computed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(20), nullable=False, server_default="1.0"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # Create item_pair_scores table
    op.create_table(
        "item_pair_scores",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item1_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clothing_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "item2_id",
            UUID(as_uuid=True),
            sa.ForeignKey("clothing_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("compatibility_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("times_paired", sa.Integer, nullable=False, server_default="0"),
        sa.Column("times_accepted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("times_rejected", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_rating_sum", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rating_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("occasion_performance", JSONB, nullable=False, server_default="{}"),
        sa.Column("weather_performance", JSONB, nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "item1_id", "item2_id", name="uq_user_item_pair"),
    )

    # Create indexes for item_pair_scores
    op.create_index("ix_item_pair_scores_user_id", "item_pair_scores", ["user_id"])
    op.create_index("ix_item_pair_scores_item1_id", "item_pair_scores", ["item1_id"])
    op.create_index("ix_item_pair_scores_item2_id", "item_pair_scores", ["item2_id"])
    op.create_index(
        "ix_item_pair_scores_compatibility", "item_pair_scores", ["user_id", "compatibility_score"]
    )

    # Create outfit_performances table
    op.create_table(
        "outfit_performances",
        sa.Column(
            "outfit_id",
            UUID(as_uuid=True),
            sa.ForeignKey("outfits.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("performance_score", sa.Numeric(5, 4), nullable=False, server_default="0"),
        sa.Column("acceptance_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("rating_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("wear_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("occasion", sa.String(50), nullable=False),
        sa.Column("weather_temp", sa.Integer, nullable=True),
        sa.Column("weather_condition", sa.String(50), nullable=True),
        sa.Column("item_composition", JSONB, nullable=False, server_default="{}"),
        sa.Column("color_composition", JSONB, nullable=False, server_default="{}"),
        sa.Column("was_modified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("modification_notes", sa.Text, nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # Create indexes for outfit_performances
    op.create_index("ix_outfit_performances_user_id", "outfit_performances", ["user_id"])
    op.create_index(
        "ix_outfit_performances_occasion", "outfit_performances", ["user_id", "occasion"]
    )

    # Create style_insights table
    op.create_table(
        "style_insights",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("insight_type", sa.String(20), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False, server_default="0.5"),
        sa.Column("supporting_data", JSONB, nullable=False, server_default="{}"),
        sa.Column("is_acknowledged", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # Create indexes for style_insights
    op.create_index("ix_style_insights_user_id", "style_insights", ["user_id"])
    op.create_index(
        "ix_style_insights_active", "style_insights", ["user_id", "is_acknowledged", "expires_at"]
    )


def downgrade() -> None:
    # Drop style_insights table and indexes
    op.drop_index("ix_style_insights_active", table_name="style_insights")
    op.drop_index("ix_style_insights_user_id", table_name="style_insights")
    op.drop_table("style_insights")

    # Drop outfit_performances table and indexes
    op.drop_index("ix_outfit_performances_occasion", table_name="outfit_performances")
    op.drop_index("ix_outfit_performances_user_id", table_name="outfit_performances")
    op.drop_table("outfit_performances")

    # Drop item_pair_scores table and indexes
    op.drop_index("ix_item_pair_scores_compatibility", table_name="item_pair_scores")
    op.drop_index("ix_item_pair_scores_item2_id", table_name="item_pair_scores")
    op.drop_index("ix_item_pair_scores_item1_id", table_name="item_pair_scores")
    op.drop_index("ix_item_pair_scores_user_id", table_name="item_pair_scores")
    op.drop_table("item_pair_scores")

    # Drop user_learning_profiles table
    op.drop_table("user_learning_profiles")
