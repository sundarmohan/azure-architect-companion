"""Store local recurring Azure subscription budgets."""

import sqlalchemy as sa
from alembic import op

revision = "0024_cost_budgets"
down_revision = "0023_compliance_reviews"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_cost_budgets",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("subscription_id", sa.Uuid(), primary_key=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_azure_cost_budgets_positive"),
    )


def downgrade():
    op.drop_table("azure_cost_budgets")
