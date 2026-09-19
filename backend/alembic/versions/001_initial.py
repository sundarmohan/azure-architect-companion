"""Initial migration - create canonical model tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-09-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create architectures table
    op.create_table(
        'architectures',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_architectures_name'), 'architectures', ['name'], unique=False)

    # Create architecture_versions table
    op.create_table(
        'architecture_versions',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('architecture_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('version_number', sa.String(50), nullable=False),
        sa.Column('status', sa.String(50), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(['architecture_id'], ['architectures.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_architecture_versions_architecture_id'), 'architecture_versions', ['architecture_id'], unique=False)

    # Create resources table
    op.create_table(
        'resources',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('architecture_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_key', sa.String(255), nullable=False),
        sa.Column('resource_type', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('location', sa.String(100), nullable=True),
        sa.Column('sku', sa.JSON(), nullable=True),
        sa.Column('properties', sa.JSON(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('parent_resource_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['architecture_version_id'], ['architecture_versions.id'], ),
        sa.ForeignKeyConstraint(['parent_resource_id'], ['resources.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resources_architecture_version_id'), 'resources', ['architecture_version_id'], unique=False)
    op.create_index(op.f('ix_resources_resource_type'), 'resources', ['resource_type'], unique=False)

    # Create relationships table
    op.create_table(
        'relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('architecture_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('target_resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('relationship_type', sa.String(100), nullable=False),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['architecture_version_id'], ['architecture_versions.id'], ),
        sa.ForeignKeyConstraint(['source_resource_id'], ['resources.id'], ),
        sa.ForeignKeyConstraint(['target_resource_id'], ['resources.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_relationships_architecture_version_id'), 'relationships', ['architecture_version_id'], unique=False)

    # Create dependencies table
    op.create_table(
        'dependencies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('architecture_version_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('depends_on_resource_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('dependency_type', sa.String(100), nullable=False),
        sa.Column('required', sa.Boolean(), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['architecture_version_id'], ['architecture_versions.id'], ),
        sa.ForeignKeyConstraint(['depends_on_resource_id'], ['resources.id'], ),
        sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dependencies_architecture_version_id'), 'dependencies', ['architecture_version_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_dependencies_architecture_version_id'), table_name='dependencies')
    op.drop_table('dependencies')
    op.drop_index(op.f('ix_relationships_architecture_version_id'), table_name='relationships')
    op.drop_table('relationships')
    op.drop_index(op.f('ix_resources_resource_type'), table_name='resources')
    op.drop_index(op.f('ix_resources_architecture_version_id'), table_name='resources')
    op.drop_table('resources')
    op.drop_index(op.f('ix_architecture_versions_architecture_id'), table_name='architecture_versions')
    op.drop_table('architecture_versions')
    op.drop_index(op.f('ix_architectures_name'), table_name='architectures')
    op.drop_table('architectures')
