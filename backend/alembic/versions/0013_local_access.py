"""Add local accounts and client-owned application data."""

import sqlalchemy as sa
from alembic import op

revision = "0013_local_access"
down_revision = "0012_preserve_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "local_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_platform_admin", sa.Boolean(), nullable=False),
        sa.Column("failed_logins", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "client_workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False, unique=True),
    )
    op.create_table(
        "client_memberships",
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("local_accounts.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint("role IN ('admin', 'editor', 'viewer')", name="ck_client_membership_role"),
    )
    op.create_table(
        "local_login_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("local_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_local_login_sessions_account_id", "local_login_sessions", ["account_id"])
    op.create_table(
        "client_audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("account_id", sa.Uuid()),
        sa.Column("client_id", sa.Uuid()),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(200)),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_client_audit_events_client_id", "client_audit_events", ["client_id"])
    op.create_table(
        "client_azure_connections",
        sa.Column("client_id", sa.Uuid(), sa.ForeignKey("client_workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("ciphertext", sa.Text(), nullable=False),
    )
    # Preserve legacy designs without granting any client implicit ownership.
    op.add_column("architectures", sa.Column("client_id", sa.Uuid()))
    op.create_foreign_key("fk_architectures_client", "architectures", "client_workspaces", ["client_id"], ["id"])
    op.create_index("ix_architectures_client_id", "architectures", ["client_id"])


def downgrade():
    op.drop_index("ix_architectures_client_id", table_name="architectures")
    op.drop_constraint("fk_architectures_client", "architectures", type_="foreignkey")
    op.drop_column("architectures", "client_id")
    for table in ("client_azure_connections", "client_audit_events", "local_login_sessions",
                  "client_memberships", "client_workspaces", "local_accounts"):
        op.drop_table(table)
