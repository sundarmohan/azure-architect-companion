"""Persist Azure connection verification and inventory failure stages."""

import sqlalchemy as sa
from alembic import op

revision = "0036_azure_collection_state"
down_revision = "0035_restore_tests"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("client_azure_connections", sa.Column(
        "connection_state", sa.String(32), nullable=False, server_default="unverified",
    ))
    op.add_column("client_azure_connections", sa.Column("last_tested_at", sa.DateTime(timezone=True)))
    op.add_column("client_azure_connections", sa.Column("last_success_at", sa.DateTime(timezone=True)))
    op.add_column("client_azure_connections", sa.Column("failure_stage", sa.String(32)))
    op.add_column("client_azure_connections", sa.Column("failure_reason", sa.String(32)))
    op.add_column("client_azure_inventory", sa.Column("failure_stage", sa.String(32)))


def downgrade():
    op.drop_column("client_azure_inventory", "failure_stage")
    op.drop_column("client_azure_connections", "failure_reason")
    op.drop_column("client_azure_connections", "failure_stage")
    op.drop_column("client_azure_connections", "last_success_at")
    op.drop_column("client_azure_connections", "last_tested_at")
    op.drop_column("client_azure_connections", "connection_state")
