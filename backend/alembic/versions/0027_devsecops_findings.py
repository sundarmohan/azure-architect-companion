"""Store sanitized repository security finding metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0027_devsecops_findings"
down_revision = "0026_incident_actions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "devsecops_findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner", sa.String(39), nullable=False),
        sa.Column("repository", sa.String(100), nullable=False),
        sa.Column("source", sa.String(60), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("commit_sha", sa.String(40)),
        sa.Column("image", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("client_id", "owner", "repository", "source", "fingerprint", name="uq_devsecops_finding_source"),
    )
    op.create_index("ix_devsecops_findings_client_id", "devsecops_findings", ["client_id"])


def downgrade():
    op.drop_table("devsecops_findings")
