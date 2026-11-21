"""Persist client-scoped Azure inventory snapshots."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from alembic import op

revision = "0015_azure_inventory"
down_revision = "0014_design_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_azure_inventory",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("resource_groups", JSONB(), nullable=False),
        sa.Column("resources", JSONB(), nullable=False),
    )


def downgrade():
    op.drop_table("client_azure_inventory")
