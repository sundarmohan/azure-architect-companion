"""Add deterministic architecture snapshot versioning.

Revision ID: 004_architecture_versioning
Revises: 003_terraform_execution
Create Date: 2026-09-30 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "004_architecture_versioning"
down_revision = "003_terraform_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("architecture_versions", sa.Column("version_sequence", sa.Integer(), nullable=True))
    op.add_column("architecture_versions", sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("architecture_versions", sa.Column("change_description", sa.Text(), nullable=True))
    op.add_column("architecture_versions", sa.Column("metadata", sa.JSON(), nullable=True))
    op.add_column("architecture_versions", sa.Column("snapshot_hash", sa.String(64), nullable=True))
    op.add_column("architecture_versions", sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("architecture_versions", sa.Column("validation_status", sa.String(50), nullable=True))
    op.add_column("architecture_versions", sa.Column("compliance_status", sa.String(50), nullable=True))

    op.execute(
        """
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY architecture_id ORDER BY created_at, id
            ) AS sequence
            FROM architecture_versions
        )
        UPDATE architecture_versions
        SET version_sequence = numbered.sequence
        FROM numbered
        WHERE architecture_versions.id = numbered.id
        """
    )
    op.alter_column("architecture_versions", "version_sequence", nullable=False)
    op.create_foreign_key(
        "fk_architecture_versions_parent",
        "architecture_versions",
        "architecture_versions",
        ["parent_version_id"],
        ["id"],
    )
    op.create_unique_constraint(
        "uq_architecture_version_number",
        "architecture_versions",
        ["architecture_id", "version_number"],
    )
    op.create_unique_constraint(
        "uq_architecture_version_sequence",
        "architecture_versions",
        ["architecture_id", "version_sequence"],
    )
    op.create_unique_constraint(
        "uq_version_resource_key",
        "resources",
        ["architecture_version_id", "resource_key"],
    )
    op.create_index("ix_architecture_versions_parent_version_id", "architecture_versions", ["parent_version_id"])
    op.create_index("ix_architecture_versions_snapshot_hash", "architecture_versions", ["snapshot_hash"])

    op.create_table(
        "architecture_version_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"]),
        sa.ForeignKeyConstraint(["architecture_version_id"], ["architecture_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_architecture_version_events_architecture_id", "architecture_version_events", ["architecture_id"])
    op.create_index("ix_architecture_version_events_architecture_version_id", "architecture_version_events", ["architecture_version_id"])
    op.create_index("ix_architecture_version_events_event_type", "architecture_version_events", ["event_type"])
    op.execute(
        "CREATE UNIQUE INDEX uq_architecture_active_version "
        "ON architecture_versions (architecture_id) WHERE status = 'ACTIVE'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_architecture_active_version")
    op.drop_index("ix_architecture_version_events_event_type", table_name="architecture_version_events")
    op.drop_index("ix_architecture_version_events_architecture_version_id", table_name="architecture_version_events")
    op.drop_index("ix_architecture_version_events_architecture_id", table_name="architecture_version_events")
    op.drop_table("architecture_version_events")
    op.drop_index("ix_architecture_versions_snapshot_hash", table_name="architecture_versions")
    op.drop_index("ix_architecture_versions_parent_version_id", table_name="architecture_versions")
    op.drop_constraint("uq_version_resource_key", "resources", type_="unique")
    op.drop_constraint("uq_architecture_version_sequence", "architecture_versions", type_="unique")
    op.drop_constraint("uq_architecture_version_number", "architecture_versions", type_="unique")
    op.drop_constraint("fk_architecture_versions_parent", "architecture_versions", type_="foreignkey")
    op.drop_column("architecture_versions", "compliance_status")
    op.drop_column("architecture_versions", "validation_status")
    op.drop_column("architecture_versions", "finalized_at")
    op.drop_column("architecture_versions", "snapshot_hash")
    op.drop_column("architecture_versions", "metadata")
    op.drop_column("architecture_versions", "change_description")
    op.drop_column("architecture_versions", "parent_version_id")
    op.drop_column("architecture_versions", "version_sequence")