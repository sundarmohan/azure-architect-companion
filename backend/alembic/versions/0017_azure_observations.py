"""Persist client-scoped Azure observation snapshots and opt-in schedules."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017_azure_observations"
down_revision = "0016_inventory_failure"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_observations",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("limitations", JSONB(), nullable=False),
    )
    op.create_table(
        "azure_observation_schedules",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("interval_minutes BETWEEN 5 AND 1440", name="ck_observation_schedule_interval"),
    )
    op.create_index("ix_azure_observation_schedules_next_run_at", "azure_observation_schedules", ["next_run_at"])


def downgrade():
    op.drop_table("azure_observation_schedules")
    op.drop_table("azure_observations")
