"""Persist local Azure Monitor threshold settings."""

import sqlalchemy as sa
from alembic import op

revision = "0034_metric_thresholds"
down_revision = "0033_compliance_history"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_metric_thresholds",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("metric", sa.String(100), nullable=False),
        sa.Column("aggregation", sa.String(12), nullable=False),
        sa.Column("unit", sa.String(40)),
        sa.Column("direction", sa.String(8), nullable=False),
        sa.Column("limit", sa.Float(), nullable=False),
    )


def downgrade():
    op.drop_table("azure_metric_thresholds")
