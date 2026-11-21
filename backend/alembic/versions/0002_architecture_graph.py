from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision="0002_architecture_graph"; down_revision="0001_initial_architecture"; branch_labels=None; depends_on=None
def upgrade():
    op.create_table("architecture_resources",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("architecture_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("resource_type",sa.String(100),nullable=False),
        sa.Column("azure_resource_type",sa.String(200)),sa.Column("name",sa.String(200),nullable=False),
        sa.Column("location",sa.String(100)),sa.Column("sku",sa.String(200)),
        sa.Column("properties",postgresql.JSONB(),nullable=False),
        sa.Column("position_x",sa.Float(),nullable=False),sa.Column("position_y",sa.Float(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.Column("updated_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["architecture_id"],["architectures.id"],ondelete="CASCADE"),sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_architecture_resources_architecture_id","architecture_resources",["architecture_id"])
    op.create_table("architecture_relationships",
        sa.Column("id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("architecture_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("source_resource_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("target_resource_id",postgresql.UUID(as_uuid=True),nullable=False),
        sa.Column("relationship_type",sa.String(80),nullable=False),sa.Column("properties",postgresql.JSONB(),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["architecture_id"],["architectures.id"],ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_resource_id"],["architecture_resources.id"],ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_resource_id"],["architecture_resources.id"],ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"))
    op.create_index("ix_architecture_relationships_architecture_id","architecture_relationships",["architecture_id"])
def downgrade():
    op.drop_index("ix_architecture_relationships_architecture_id",table_name="architecture_relationships"); op.drop_table("architecture_relationships")
    op.drop_index("ix_architecture_resources_architecture_id",table_name="architecture_resources"); op.drop_table("architecture_resources")
