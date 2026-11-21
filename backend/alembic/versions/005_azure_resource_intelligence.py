"""Add read-only Azure Resource Intelligence snapshots and preflight references.

Revision ID: 005_azure_resource_intelligence
Revises: 004_architecture_versioning
Create Date: 2026-10-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "005_azure_resource_intelligence"
down_revision = "004_architecture_versioning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "azure_connections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("subscription_id", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("credential_mode", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "subscription_id", name="uq_azure_connection_scope"),
    )
    op.create_index("ix_azure_connections_subscription_id", "azure_connections", ["subscription_id"])

    op.create_table(
        "azure_intelligence_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subscription_id", sa.String(64), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("snapshot_sequence", sa.Integer(), nullable=False),
        sa.Column("snapshot_hash", sa.String(64), nullable=False),
        sa.Column("source_version", sa.String(50), nullable=False),
        sa.Column("terraform_provider_version", sa.String(50), nullable=True),
        sa.Column("subscription_metadata", sa.JSON(), nullable=False),
        sa.Column("resource_groups", sa.JSON(), nullable=False),
        sa.Column("resource_types", sa.JSON(), nullable=False),
        sa.Column("regions", sa.JSON(), nullable=False),
        sa.Column("skus", sa.JSON(), nullable=False),
        sa.Column("providers", sa.JSON(), nullable=False),
        sa.Column("quotas", sa.JSON(), nullable=False),
        sa.Column("resources", sa.JSON(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["azure_connections.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id", "snapshot_sequence", name="uq_azure_snapshot_sequence"),
    )
    op.create_index("ix_azure_intelligence_snapshots_connection_id", "azure_intelligence_snapshots", ["connection_id"])
    op.create_index("ix_azure_intelligence_snapshots_subscription_id", "azure_intelligence_snapshots", ["subscription_id"])
    op.create_index("ix_azure_intelligence_snapshots_snapshot_hash", "azure_intelligence_snapshots", ["snapshot_hash"])
    op.create_index("ix_azure_intelligence_snapshots_expires_at", "azure_intelligence_snapshots", ["expires_at"])

    op.create_table(
        "azure_preflight_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("azure_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("findings", sa.JSON(), nullable=False),
        sa.Column("result_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"]),
        sa.ForeignKeyConstraint(["architecture_version_id"], ["architecture_versions.id"]),
        sa.ForeignKeyConstraint(["azure_snapshot_id"], ["azure_intelligence_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("architecture_id", "architecture_version_id", "azure_snapshot_id", "architecture_snapshot_hash", "status", "result_hash"):
        op.create_index(f"ix_azure_preflight_results_{column}", "azure_preflight_results", [column])

    op.add_column("terraform_executions", sa.Column("azure_snapshot_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("terraform_executions", sa.Column("azure_preflight_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_terraform_execution_azure_snapshot", "terraform_executions", "azure_intelligence_snapshots", ["azure_snapshot_id"], ["id"])
    op.create_foreign_key("fk_terraform_execution_azure_preflight", "terraform_executions", "azure_preflight_results", ["azure_preflight_id"], ["id"])
    op.create_index("ix_terraform_executions_azure_snapshot_id", "terraform_executions", ["azure_snapshot_id"])
    op.create_index("ix_terraform_executions_azure_preflight_id", "terraform_executions", ["azure_preflight_id"])


def downgrade() -> None:
    op.drop_index("ix_terraform_executions_azure_preflight_id", table_name="terraform_executions")
    op.drop_index("ix_terraform_executions_azure_snapshot_id", table_name="terraform_executions")
    op.drop_constraint("fk_terraform_execution_azure_preflight", "terraform_executions", type_="foreignkey")
    op.drop_constraint("fk_terraform_execution_azure_snapshot", "terraform_executions", type_="foreignkey")
    op.drop_column("terraform_executions", "azure_preflight_id")
    op.drop_column("terraform_executions", "azure_snapshot_id")
    for column in ("result_hash", "status", "architecture_snapshot_hash", "azure_snapshot_id", "architecture_version_id", "architecture_id"):
        op.drop_index(f"ix_azure_preflight_results_{column}", table_name="azure_preflight_results")
    op.drop_table("azure_preflight_results")
    op.drop_index("ix_azure_intelligence_snapshots_expires_at", table_name="azure_intelligence_snapshots")
    op.drop_index("ix_azure_intelligence_snapshots_snapshot_hash", table_name="azure_intelligence_snapshots")
    op.drop_index("ix_azure_intelligence_snapshots_subscription_id", table_name="azure_intelligence_snapshots")
    op.drop_index("ix_azure_intelligence_snapshots_connection_id", table_name="azure_intelligence_snapshots")
    op.drop_table("azure_intelligence_snapshots")
    op.drop_index("ix_azure_connections_subscription_id", table_name="azure_connections")
    op.drop_table("azure_connections")