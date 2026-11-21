from alembic import op
from sqlalchemy.dialects import postgresql
import sqlalchemy as sa

revision = "0010_monitoring_signal_snapshots"
down_revision = "0009_monitoring_subscriptions"
branch_labels = None
depends_on = None


def upgrade():
    for column in ("metrics", "alerts", "incidents", "unused_analysis"):
        op.add_column("monitoring_subscriptions", sa.Column(column, postgresql.JSONB(), nullable=False, server_default="{}" if column != "alerts" and column != "incidents" else "[]"))


def downgrade():
    for column in ("unused_analysis", "incidents", "alerts", "metrics"):
        op.drop_column("monitoring_subscriptions", column)
