"""Add design organization, revision snapshots, and status history."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0014_design_lifecycle"
down_revision = "0013_local_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("architectures", sa.Column("project", sa.String(160)))
    op.create_table(
        "design_revisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("architecture_id", sa.Uuid(), sa.ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("architecture_id", "number", name="uq_design_revision_number"),
    )
    op.create_table(
        "design_lifecycle_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("architecture_id", sa.Uuid(), sa.ForeignKey("architectures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(30), nullable=False),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("actor", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_design_lifecycle_events_architecture_id", "design_lifecycle_events", ["architecture_id"])
    # Phase 1 accepted arbitrary status values. Keep archived records and
    # reference-only rows intact. A pre-workflow approval is not authoritative.
    op.execute(sa.text("""
        INSERT INTO design_lifecycle_events
            (id, architecture_id, action, from_status, to_status, note, actor)
        SELECT gen_random_uuid(), id, 'status_migrated', status, 'draft',
            'Previous status predated the approval workflow.', 'system:migration'
        FROM architectures WHERE client_id IS NOT NULL AND status NOT IN ('draft', 'archived')
    """))
    op.execute(sa.text("""
        UPDATE architectures SET status = 'draft'
        WHERE client_id IS NOT NULL AND status NOT IN ('draft', 'archived')
    """))
    op.create_check_constraint(
        "ck_architecture_status", "architectures",
        "client_id IS NULL OR status IN ('draft', 'in_review', 'approved', 'archived')",
    )


def downgrade():
    op.drop_constraint("ck_architecture_status", "architectures", type_="check")
    op.drop_table("design_lifecycle_events")
    op.drop_table("design_revisions")
    op.drop_column("architectures", "project")
