from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0007_provider_config_persistence"
down_revision = "0006_v25_hierarchy_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", name="uq_provider_configurations_provider"),
    )
    op.create_index(
        "ix_provider_configurations_provider",
        "provider_configurations",
        ["provider"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_provider_configurations_provider", table_name="provider_configurations")
    op.drop_table("provider_configurations")