from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_v25_hierarchy_foundation"
down_revision = "0005_v244_stabilization"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "architecture_resources",
        sa.Column("parent_resource_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_resource_parent",
        "architecture_resources",
        "architecture_resources",
        ["parent_resource_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_architecture_resources_parent_resource_id",
        "architecture_resources",
        ["parent_resource_id"],
    )


def downgrade():
    op.drop_index("ix_architecture_resources_parent_resource_id", table_name="architecture_resources")
    op.drop_constraint("fk_resource_parent", "architecture_resources", type_="foreignkey")
    op.drop_column("architecture_resources", "parent_resource_id")
