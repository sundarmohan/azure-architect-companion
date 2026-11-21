from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009_monitoring_subscriptions"
down_revision = "0008_v219_incident_alert_ops"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitoring_subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tenant_id", sa.String(100)),
        sa.Column("service_principal_provider", sa.String(80), nullable=False),
        sa.Column("connection_state", sa.String(50), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("resources", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id", name="uq_monitoring_subscriptions_subscription_id"),
    )
    op.create_index("ix_monitoring_subscriptions_subscription_id", "monitoring_subscriptions", ["subscription_id"])


def downgrade():
    op.drop_index("ix_monitoring_subscriptions_subscription_id", table_name="monitoring_subscriptions")
    op.drop_table("monitoring_subscriptions")
