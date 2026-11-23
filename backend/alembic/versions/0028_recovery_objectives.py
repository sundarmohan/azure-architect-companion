"""Store recovery objectives for configured Azure subscriptions."""

import sqlalchemy as sa
from alembic import op

revision = "0028_recovery_objectives"
down_revision = "0027_devsecops_findings"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_recovery_objectives",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("rpo_hours", sa.Integer(), nullable=False),
        sa.Column("rto_minutes", sa.Integer(), nullable=False),
        sa.CheckConstraint("rpo_hours BETWEEN 1 AND 8760", name="ck_azure_recovery_objectives_rpo"),
        sa.CheckConstraint("rto_minutes BETWEEN 1 AND 525600", name="ck_azure_recovery_objectives_rto"),
    )


def downgrade():
    op.drop_table("azure_recovery_objectives")
