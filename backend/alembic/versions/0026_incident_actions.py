"""Track local corrective and preventive actions for Azure health incidents."""

import sqlalchemy as sa
from alembic import op

revision = "0026_incident_actions"
down_revision = "0025_vulnerability_acceptance"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_health_incident_actions",
        sa.Column("incident_id", sa.Uuid(), sa.ForeignKey("azure_health_incidents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("owner", sa.String(120), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("azure_health_incident_actions")
