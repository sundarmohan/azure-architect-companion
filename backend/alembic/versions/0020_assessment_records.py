"""Persist authorized assessment records, imported findings and status history."""

import sqlalchemy as sa
from alembic import op

revision = "0020_assessment_records"
down_revision = "0019_security_tracking"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "security_assessments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False),
        sa.Column("authorization", sa.Text(), nullable=False),
        sa.Column("environment", sa.String(80)),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("window_end > window_start", name="ck_assessment_window"),
    )
    op.create_index("ix_security_assessments_client_id", "security_assessments", ["client_id"])
    op.create_table(
        "security_assessment_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("assessment_id", sa.Uuid(), sa.ForeignKey("security_assessments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("tool_version", sa.String(100)),
        sa.Column("methodology", sa.String(400)),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("owner", sa.String(120)),
        sa.Column("due_date", sa.Date()),
        sa.Column("retest_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("assessment_id", "source", "external_id", name="uq_assessment_finding_source"),
    )
    op.create_index("ix_security_assessment_findings_assessment_id", "security_assessment_findings", ["assessment_id"])
    op.create_table(
        "security_assessment_finding_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("finding_id", sa.Uuid(), sa.ForeignKey("security_assessment_findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_security_assessment_finding_events_finding_id", "security_assessment_finding_events", ["finding_id"])


def downgrade():
    op.drop_table("security_assessment_finding_events")
    op.drop_table("security_assessment_findings")
    op.drop_table("security_assessments")
