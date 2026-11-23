"""Link human-created Azure health incidents to acknowledged evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0022_health_incidents"
down_revision = "0021_health_acknowledgements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_health_incidents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("evidence_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("owner", sa.String(120)),
        sa.Column("rca_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["client_id", "subscription_id", "evidence_id"],
            ["azure_health_acknowledgements.client_id", "azure_health_acknowledgements.subscription_id",
             "azure_health_acknowledgements.evidence_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("client_id", "subscription_id", "evidence_id", name="uq_health_incident_evidence"),
    )
    op.create_index("ix_health_incident_scope_created", "azure_health_incidents",
                    ["client_id", "subscription_id", "created_at"])


def downgrade():
    op.drop_table("azure_health_incidents")
