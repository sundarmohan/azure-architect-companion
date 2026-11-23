"""Store append-only restore test evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0035_restore_tests"
down_revision = "0034_metric_thresholds"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "azure_restore_tests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("resource_name", sa.String(200), nullable=False),
        sa.Column("tested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("recovery_minutes", sa.Integer()),
        sa.Column("evidence_reference", sa.String(500)),
        sa.Column("notes", sa.Text()),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("outcome IN ('passed', 'failed', 'partial')", name="ck_azure_restore_test_outcome"),
        sa.CheckConstraint("recovery_minutes IS NULL OR recovery_minutes BETWEEN 1 AND 525600",
                           name="ck_azure_restore_test_duration"),
    )
    op.create_index("ix_azure_restore_test_scope", "azure_restore_tests",
                    ["client_id", "subscription_id", "tested_at"])


def downgrade():
    op.drop_index("ix_azure_restore_test_scope", table_name="azure_restore_tests")
    op.drop_table("azure_restore_tests")
