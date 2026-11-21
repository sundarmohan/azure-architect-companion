"""Add compliance framework, control and policy tables.

These models (Milestone 5) were never covered by a migration, so the
compliance endpoints failed on PostgreSQL deployments.

Revision ID: 007_compliance_frameworks
Revises: 006_conformance
Create Date: 2026-11-21 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "007_compliance_frameworks"
down_revision = "006_conformance"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("compliance_frameworks"):
        op.create_table(
            "compliance_frameworks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("framework_name", sa.String(100), nullable=False),
            sa.Column("framework_version", sa.String(50), nullable=False),
            sa.Column("display_name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_compliance_frameworks_framework_name",
            "compliance_frameworks",
            ["framework_name"],
            unique=True,
        )

    if not _has_table("compliance_controls"):
        op.create_table(
            "compliance_controls",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("framework_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("control_code", sa.String(100), nullable=False),
            sa.Column("title", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("category", sa.String(50), nullable=False),
            sa.Column("evaluation_type", sa.String(50), nullable=False),
            sa.Column("rule_version", sa.String(50), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["framework_id"], ["compliance_frameworks.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_compliance_controls_framework_id",
            "compliance_controls",
            ["framework_id"],
        )

    if not _has_table("compliance_control_policies"):
        op.create_table(
            "compliance_control_policies",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("control_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("policy_level", sa.String(50), nullable=False),
            sa.Column("default_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["control_id"], ["compliance_controls.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_compliance_control_policies_control_id",
            "compliance_control_policies",
            ["control_id"],
        )


def downgrade() -> None:
    op.drop_index("ix_compliance_control_policies_control_id", table_name="compliance_control_policies")
    op.drop_table("compliance_control_policies")
    op.drop_index("ix_compliance_controls_framework_id", table_name="compliance_controls")
    op.drop_table("compliance_controls")
    op.drop_index("ix_compliance_frameworks_framework_name", table_name="compliance_frameworks")
    op.drop_table("compliance_frameworks")
