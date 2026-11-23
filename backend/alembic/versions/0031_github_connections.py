"""Store an encrypted GitHub connection for each client."""

import sqlalchemy as sa
from alembic import op

revision = "0031_github_connections"
down_revision = "0030_framework_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_github_connections",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner", sa.String(39), nullable=False),
        sa.Column("repository", sa.String(100), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
    )


def downgrade():
    op.drop_table("client_github_connections")
