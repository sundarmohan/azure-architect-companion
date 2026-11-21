from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0004_visual_hierarchy"
down_revision="0003_azure_hierarchy"
branch_labels=None
depends_on=None

def upgrade():
    op.add_column("azure_resource_groups", sa.Column("subscription_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_rg_subscription", "azure_resource_groups", "azure_subscriptions", ["subscription_id"], ["id"], ondelete="SET NULL")
    op.add_column("architecture_resources", sa.Column("resource_group_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_resource_rg", "architecture_resources", "azure_resource_groups", ["resource_group_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_architecture_resources_resource_group_id", "architecture_resources", ["resource_group_id"])

def downgrade():
    op.drop_index("ix_architecture_resources_resource_group_id", table_name="architecture_resources")
    op.drop_constraint("fk_resource_rg", "architecture_resources", type_="foreignkey")
    op.drop_column("architecture_resources", "resource_group_id")
    op.drop_constraint("fk_rg_subscription", "azure_resource_groups", type_="foreignkey")
    op.drop_column("azure_resource_groups", "subscription_id")
