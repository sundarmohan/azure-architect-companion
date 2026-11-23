"""Persist reviews and corrective action for selected Azure technical topics."""

import sqlalchemy as sa
from alembic import op

revision = "0023_compliance_reviews"
down_revision = "0022_health_incidents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "compliance_reviews",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("topic", sa.String(24), primary_key=True),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("action", sa.Text()),
        sa.Column("owner", sa.String(120)),
        sa.Column("due_date", sa.Date()),
        sa.Column("action_status", sa.String(24)),
        sa.Column("evidence_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("compliance_reviews")
