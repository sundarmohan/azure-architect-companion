"""Add immutable conformance assessments, findings, and audit events.

Revision ID: 006_conformance
Revises: 005_azure_resource_intelligence
Create Date: 2026-10-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "006_conformance"
down_revision = "005_azure_resource_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conformance_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("azure_snapshot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("terraform_execution_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("architecture_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("azure_snapshot_hash", sa.String(64), nullable=False),
        sa.Column("terraform_generation_hash", sa.String(64), nullable=True),
        sa.Column("terraform_plan_hash", sa.String(64), nullable=True),
        sa.Column("terraform_execution_state", sa.String(50), nullable=True),
        sa.Column("engine_version", sa.String(50), nullable=False),
        sa.Column("comparison_hash", sa.String(64), nullable=False),
        sa.Column("overall_status", sa.String(50), nullable=False),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"]),
        sa.ForeignKeyConstraint(["architecture_version_id"], ["architecture_versions.id"]),
        sa.ForeignKeyConstraint(["azure_snapshot_id"], ["azure_intelligence_snapshots.id"]),
        sa.ForeignKeyConstraint(["terraform_execution_id"], ["terraform_executions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("architecture_id", "architecture_version_id", "azure_snapshot_id", "terraform_execution_id", "architecture_snapshot_hash", "azure_snapshot_hash", "comparison_hash", "overall_status"):
        op.create_index(f"ix_conformance_assessments_{column}", "conformance_assessments", [column])

    op.create_table(
        "conformance_findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("finding_key", sa.String(64), nullable=False),
        sa.Column("resource_key", sa.String(255), nullable=True),
        sa.Column("resource_type", sa.String(255), nullable=True),
        sa.Column("actual_resource_id", sa.Text(), nullable=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("desired_value_safe", sa.JSON(), nullable=True),
        sa.Column("actual_value_safe", sa.JSON(), nullable=True),
        sa.Column("property_path", sa.String(500), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("desired_version", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["conformance_assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "finding_key", name="uq_conformance_finding_key"),
    )
    for column in ("assessment_id", "resource_key", "category", "severity", "status"):
        op.create_index(f"ix_conformance_findings_{column}", "conformance_findings", [column])

    op.create_table(
        "conformance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["conformance_assessments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conformance_events_assessment_id", "conformance_events", ["assessment_id"])
    op.create_index("ix_conformance_events_event_type", "conformance_events", ["event_type"])


def downgrade() -> None:
    raise RuntimeError("Downgrade blocked: export or archive immutable conformance history first")