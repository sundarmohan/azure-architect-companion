"""Preserve saved Azure Security evidence linked by incident investigators."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032_incident_security_links"
down_revision = "0031_github_connections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_incident_security_evidence",
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("azure_health_incidents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("finding_id", sa.String(64), primary_key=True),
        sa.Column("source", sa.String(120), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("resource_id", sa.Text()),
        sa.Column("evidence", JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True)),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("azure_incident_security_evidence")
