"""Store manual applicability and outcomes for versioned framework reviews."""

import sqlalchemy as sa
from alembic import op

revision = "0030_framework_reviews"
down_revision = "0029_vulnerability_slas"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("compliance_reviews", sa.Column("applicability", sa.String(20)))
    op.add_column("compliance_reviews", sa.Column("outcome", sa.String(24)))


def downgrade():
    op.drop_column("compliance_reviews", "outcome")
    op.drop_column("compliance_reviews", "applicability")
