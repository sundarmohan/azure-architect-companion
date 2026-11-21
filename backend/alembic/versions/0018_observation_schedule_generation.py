"""Identify each administrator revision of an observation schedule."""

import sqlalchemy as sa
from alembic import op

revision = "0018_schedule_generation"
down_revision = "0017_azure_observations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "azure_observation_schedules",
        sa.Column("generation", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
    )


def downgrade():
    op.drop_column("azure_observation_schedules", "generation")
