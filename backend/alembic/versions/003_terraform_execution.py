"""Add Terraform execution lifecycle tables.

Revision ID: 003_terraform_execution
Revises: 002_catalog
Create Date: 2026-09-30 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "003_terraform_execution"
down_revision = "002_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terraform_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("architecture_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("generator_version", sa.String(50), nullable=True),
        sa.Column("generation_hash", sa.String(64), nullable=True),
        sa.Column("workspace_key", sa.String(255), nullable=True),
        sa.Column("terraform_version", sa.String(100), nullable=True),
        sa.Column("plan_filename", sa.String(255), nullable=True),
        sa.Column("plan_artifact_hash", sa.String(64), nullable=True),
        sa.Column("plan_summary", sa.JSON(), nullable=True),
        sa.Column("has_destructive_changes", sa.Boolean(), nullable=False),
        sa.Column("compliance_frameworks", sa.JSON(), nullable=True),
        sa.Column("command_results", sa.JSON(), nullable=True),
        sa.Column("approved_generation_hash", sa.String(64), nullable=True),
        sa.Column("approved_plan_hash", sa.String(64), nullable=True),
        sa.Column("approved_by", sa.String(255), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_by", sa.String(255), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["architecture_id"], ["architectures.id"]),
        sa.ForeignKeyConstraint(
            ["architecture_version_id"], ["architecture_versions.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_terraform_executions_architecture_id"),
        "terraform_executions",
        ["architecture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_terraform_executions_architecture_version_id"),
        "terraform_executions",
        ["architecture_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_terraform_executions_state"),
        "terraform_executions",
        ["state"],
        unique=False,
    )

    op.create_table(
        "terraform_execution_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["terraform_executions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_terraform_execution_events_execution_id"),
        "terraform_execution_events",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_terraform_execution_events_event_type"),
        "terraform_execution_events",
        ["event_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_terraform_execution_events_event_type"),
        table_name="terraform_execution_events",
    )
    op.drop_index(
        op.f("ix_terraform_execution_events_execution_id"),
        table_name="terraform_execution_events",
    )
    op.drop_table("terraform_execution_events")
    op.drop_index(
        op.f("ix_terraform_executions_state"),
        table_name="terraform_executions",
    )
    op.drop_index(
        op.f("ix_terraform_executions_architecture_version_id"),
        table_name="terraform_executions",
    )
    op.drop_index(
        op.f("ix_terraform_executions_architecture_id"),
        table_name="terraform_executions",
    )
    op.drop_table("terraform_executions")
