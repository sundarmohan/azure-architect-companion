from alembic import op
import sqlalchemy as sa

revision = "0011_monitoring_signal_states"
down_revision = "0010_monitoring_signal_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("metrics_state", "alerts_state", "incidents_state"):
        op.add_column("monitoring_subscriptions", sa.Column(column, sa.String(50), nullable=False, server_default="not_checked"))


def downgrade():
    for column in ("incidents_state", "alerts_state", "metrics_state"):
        op.drop_column("monitoring_subscriptions", column)
