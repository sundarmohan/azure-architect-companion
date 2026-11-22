"""Persist explicit acknowledgements of saved Azure health evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0021_health_acknowledgements"
down_revision = "0020_assessment_records"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_health_acknowledgements",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("evidence_id", sa.String(64), primary_key=True),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("health", sa.String(16), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("azure_health_acknowledgements")
