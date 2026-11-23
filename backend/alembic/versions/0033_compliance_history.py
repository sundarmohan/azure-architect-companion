"""Preserve immutable summaries of compliance review changes."""

from uuid import uuid4

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0033_compliance_history"
down_revision = "0032_incident_security_links"
branch_labels = None
depends_on = None


def upgrade():
    history = op.create_table(
        "compliance_review_history",
        sa.Column("id", sa.Uuid(), primary_key=True, default=uuid4),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("subscription_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.Uuid(), sa.ForeignKey("local_accounts.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("applicability", sa.String(20)),
        sa.Column("outcome", sa.String(24)),
        sa.Column("action_status", sa.String(24)),
        sa.Column("due_date", sa.Date()),
        sa.Column("evidence_at", sa.DateTime(timezone=True)),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("changed_fields", JSONB(), nullable=False),
        sa.Column("baseline", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_compliance_review_history_scope", "compliance_review_history",
                    ["client_id", "subscription_id", "topic", "recorded_at", "id"])
    fields = (
        "client_id", "subscription_id", "topic", "state", "applicability",
        "outcome", "action_status", "due_date", "evidence_at",
    )
    reviews = sa.table("compliance_reviews", *(sa.column(field) for field in (*fields, "updated_at")))
    statement = sa.insert(history).from_select(
        [*fields, "recorded_at", "changed_fields", "baseline", "id"],
        sa.select(*(reviews.c[field] for field in fields), reviews.c.updated_at,
                  sa.cast(sa.literal("[]"), JSONB), sa.true(), sa.func.gen_random_uuid()),
    )
    op.execute(statement)


def downgrade():
    op.drop_table("compliance_review_history")
