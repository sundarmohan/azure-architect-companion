from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0008_v219_incident_alert_ops"
down_revision = "0007_provider_config_persistence"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitoring_incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("owner_id", sa.String(length=120), nullable=True),
        sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("affected_resource_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_alert_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_incidents_architecture_id", "monitoring_incidents", ["architecture_id"], unique=False)
    op.create_index("ix_monitoring_incidents_status", "monitoring_incidents", ["status"], unique=False)

    op.create_table(
        "monitoring_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("signal_state", sa.String(length=60), nullable=True),
        sa.Column("health_status", sa.String(length=60), nullable=True),
        sa.Column("resource_name", sa.String(length=250), nullable=True),
        sa.Column("resource_type", sa.String(length=120), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=400), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["monitoring_incidents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["resource_id"], ["architecture_resources.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["azure_subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_monitoring_alerts_architecture_id", "monitoring_alerts", ["architecture_id"], unique=False)
    op.create_index("ix_monitoring_alerts_detected_at", "monitoring_alerts", ["detected_at"], unique=False)
    op.create_index("ix_monitoring_alerts_fingerprint", "monitoring_alerts", ["fingerprint"], unique=False)
    op.create_index("ix_monitoring_alerts_incident_id", "monitoring_alerts", ["incident_id"], unique=False)
    op.create_index("ix_monitoring_alerts_resource_id", "monitoring_alerts", ["resource_id"], unique=False)
    op.create_index("ix_monitoring_alerts_status", "monitoring_alerts", ["status"], unique=False)
    op.create_index("ix_monitoring_alerts_subscription_id", "monitoring_alerts", ["subscription_id"], unique=False)


def downgrade():
    op.drop_index("ix_monitoring_alerts_subscription_id", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_status", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_resource_id", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_incident_id", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_fingerprint", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_detected_at", table_name="monitoring_alerts")
    op.drop_index("ix_monitoring_alerts_architecture_id", table_name="monitoring_alerts")
    op.drop_table("monitoring_alerts")

    op.drop_index("ix_monitoring_incidents_status", table_name="monitoring_incidents")
    op.drop_index("ix_monitoring_incidents_architecture_id", table_name="monitoring_incidents")
    op.drop_table("monitoring_incidents")
