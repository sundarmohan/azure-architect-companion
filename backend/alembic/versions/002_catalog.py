"""Add Resource Catalog tables

Revision ID: 002_catalog
Revises: 001_initial
Create Date: 2026-09-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_catalog'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create resource_catalog table
    op.create_table(
        'resource_catalog',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('resource_type', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('category', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('version', sa.String(50), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('properties_schema', sa.JSON(), nullable=True),
        sa.Column('default_properties', sa.JSON(), nullable=True),
        sa.Column('terraform_mapping', sa.JSON(), nullable=True),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resource_catalog_provider'), 'resource_catalog', ['provider'], unique=False)
    op.create_index(op.f('ix_resource_catalog_resource_type'), 'resource_catalog', ['resource_type'], unique=False)
    op.create_index(op.f('ix_resource_catalog_category'), 'resource_catalog', ['category'], unique=False)

    # Create catalog_dependencies table
    op.create_table(
        'catalog_dependencies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_type_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('depends_on_resource_type', sa.String(255), nullable=False),
        sa.Column('dependency_classification', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['resource_type_id'], ['resource_catalog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_dependencies_resource_type_id'), 'catalog_dependencies', ['resource_type_id'], unique=False)

    # Create catalog_hierarchy table
    op.create_table(
        'catalog_hierarchy',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_resource_type_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('child_resource_type_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['child_resource_type_id'], ['resource_catalog.id'], ),
        sa.ForeignKeyConstraint(['parent_resource_type_id'], ['resource_catalog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_hierarchy_parent_resource_type_id'), 'catalog_hierarchy', ['parent_resource_type_id'], unique=False)

    # Create catalog_networking_requirements table
    op.create_table(
        'catalog_networking_requirements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_catalog_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requirement', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['resource_catalog_id'], ['resource_catalog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_networking_requirements_resource_catalog_id'), 'catalog_networking_requirements', ['resource_catalog_id'], unique=False)

    # Create catalog_security_requirements table
    op.create_table(
        'catalog_security_requirements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_catalog_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requirement', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['resource_catalog_id'], ['resource_catalog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_security_requirements_resource_catalog_id'), 'catalog_security_requirements', ['resource_catalog_id'], unique=False)

    # Create catalog_monitoring_requirements table
    op.create_table(
        'catalog_monitoring_requirements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_catalog_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requirement', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['resource_catalog_id'], ['resource_catalog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_monitoring_requirements_resource_catalog_id'), 'catalog_monitoring_requirements', ['resource_catalog_id'], unique=False)

    # Create catalog_backup_requirements table
    op.create_table(
        'catalog_backup_requirements',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('resource_catalog_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('requirement', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['resource_catalog_id'], ['resource_catalog.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_catalog_backup_requirements_resource_catalog_id'), 'catalog_backup_requirements', ['resource_catalog_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_catalog_backup_requirements_resource_catalog_id'), table_name='catalog_backup_requirements')
    op.drop_table('catalog_backup_requirements')
    op.drop_index(op.f('ix_catalog_monitoring_requirements_resource_catalog_id'), table_name='catalog_monitoring_requirements')
    op.drop_table('catalog_monitoring_requirements')
    op.drop_index(op.f('ix_catalog_security_requirements_resource_catalog_id'), table_name='catalog_security_requirements')
    op.drop_table('catalog_security_requirements')
    op.drop_index(op.f('ix_catalog_networking_requirements_resource_catalog_id'), table_name='catalog_networking_requirements')
    op.drop_table('catalog_networking_requirements')
    op.drop_index(op.f('ix_catalog_hierarchy_parent_resource_type_id'), table_name='catalog_hierarchy')
    op.drop_table('catalog_hierarchy')
    op.drop_index(op.f('ix_catalog_dependencies_resource_type_id'), table_name='catalog_dependencies')
    op.drop_table('catalog_dependencies')
    op.drop_index(op.f('ix_resource_catalog_category'), table_name='resource_catalog')
    op.drop_index(op.f('ix_resource_catalog_resource_type'), table_name='resource_catalog')
    op.drop_index(op.f('ix_resource_catalog_provider'), table_name='resource_catalog')
    op.drop_table('resource_catalog')
