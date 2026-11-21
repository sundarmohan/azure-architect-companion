"""Record the cause of an incomplete Azure inventory refresh."""

import sqlalchemy as sa
from alembic import op

revision = "0016_inventory_failure"
down_revision = "0015_azure_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("client_azure_inventory", sa.Column("failure_reason", sa.String(32)))


def downgrade():
    op.drop_column("client_azure_inventory", "failure_reason")
