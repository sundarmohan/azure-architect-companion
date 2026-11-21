from alembic import op
import sqlalchemy as sa

revision = "0012_preserve_snapshots"
down_revision = "0011_monitoring_signal_states"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("monitoring_subscriptions", sa.Column("refresh_state", sa.String(50), nullable=False, server_default="not_checked"))
    op.add_column("monitoring_subscriptions", sa.Column("refresh_error", sa.Text(), nullable=True))
    op.add_column("monitoring_subscriptions", sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("monitoring_subscriptions", "last_successful_at")
    op.drop_column("monitoring_subscriptions", "refresh_error")
    op.drop_column("monitoring_subscriptions", "refresh_state")
