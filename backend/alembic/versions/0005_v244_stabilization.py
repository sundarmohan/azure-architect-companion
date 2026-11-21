from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0005_v244_stabilization"
down_revision = "0004_visual_hierarchy"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "azure_resource_groups",
        sa.Column("position_x", sa.Float(), nullable=False, server_default="80"),
    )
    op.add_column(
        "azure_resource_groups",
        sa.Column("position_y", sa.Float(), nullable=False, server_default="120"),
    )

    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT
                    id,
                    architecture_id,
                    source_resource_id,
                    target_resource_id,
                    relationship_type,
                    ROW_NUMBER() OVER (
                        PARTITION BY architecture_id, source_resource_id, target_resource_id, relationship_type
                        ORDER BY created_at NULLS LAST, id
                    ) AS rn
                FROM architecture_relationships
            )
            DELETE FROM architecture_relationships ar
            USING ranked r
            WHERE ar.id = r.id
              AND r.rn > 1
            """
        )
    )

    op.create_unique_constraint(
        "uq_architecture_relationship",
        "architecture_relationships",
        [
            "architecture_id",
            "source_resource_id",
            "target_resource_id",
            "relationship_type",
        ],
    )

    op.alter_column("azure_resource_groups", "position_x", server_default=None)
    op.alter_column("azure_resource_groups", "position_y", server_default=None)


def downgrade():
    op.drop_constraint(
        "uq_architecture_relationship",
        "architecture_relationships",
        type_="unique",
    )
    op.drop_column("azure_resource_groups", "position_y")
    op.drop_column("azure_resource_groups", "position_x")
