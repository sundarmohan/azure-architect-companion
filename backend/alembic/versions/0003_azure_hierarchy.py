from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0003_azure_hierarchy"; down_revision="0002_architecture_graph"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("azure_subscriptions",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("architecture_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("name",sa.String(200),nullable=False), sa.Column("subscription_id",sa.String(100)),
        sa.Column("tenant_id",sa.String(100)), sa.Column("environment",sa.String(50),nullable=False),
        sa.Column("properties",postgresql.JSONB(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["architecture_id"],["architectures.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_azure_subscriptions_architecture_id","azure_subscriptions",["architecture_id"])
    op.create_table("azure_resource_groups",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("architecture_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("name",sa.String(200),nullable=False), sa.Column("location",sa.String(100),nullable=False),
        sa.Column("tags",postgresql.JSONB(),nullable=False),sa.Column("properties",postgresql.JSONB(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["architecture_id"],["architectures.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_azure_resource_groups_architecture_id","azure_resource_groups",["architecture_id"])
    op.create_table("architecture_dependencies",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("architecture_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("resource_type",sa.String(100),nullable=False),sa.Column("dependency_type",sa.String(100),nullable=False),
        sa.Column("required",sa.Boolean(),nullable=False),sa.Column("auto_create_allowed",sa.Boolean(),nullable=False),
        sa.Column("notes",sa.Text()),sa.Column("properties",postgresql.JSONB(),nullable=False),
        sa.ForeignKeyConstraint(["architecture_id"],["architectures.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_architecture_dependencies_architecture_id","architecture_dependencies",["architecture_id"])
def downgrade():
    op.drop_index("ix_architecture_dependencies_architecture_id",table_name="architecture_dependencies");op.drop_table("architecture_dependencies")
    op.drop_index("ix_azure_resource_groups_architecture_id",table_name="azure_resource_groups");op.drop_table("azure_resource_groups")
    op.drop_index("ix_azure_subscriptions_architecture_id",table_name="azure_subscriptions");op.drop_table("azure_subscriptions")
