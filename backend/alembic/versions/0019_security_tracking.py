"""Store optional security polling and finding tracking per client subscription."""

import sqlalchemy as sa
from alembic import op

revision = "0019_security_tracking"
down_revision = "0018_schedule_generation"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("azure_observation_schedules", sa.Column("include_security", sa.Boolean(),
                                                         nullable=False, server_default=sa.false()))
    op.create_table(
        "azure_security_tracking",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("finding_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(120)),
        sa.Column("due_date", sa.Date()),
        sa.CheckConstraint("status IN ('open','in_progress','resolved','accepted')", name="ck_security_tracking_status"),
    )


def downgrade():
    op.drop_table("azure_security_tracking")
    op.drop_column("azure_observation_schedules", "include_security")
