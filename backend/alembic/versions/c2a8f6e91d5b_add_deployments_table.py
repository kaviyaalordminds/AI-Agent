"""add deployments table

Revision ID: c2a8f6e91d5b
Revises: b7d4e1f9a3c6
Create Date: 2026-08-17 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c2a8f6e91d5b'
down_revision: Union[str, None] = 'b7d4e1f9a3c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'deployments',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('website_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column(
            'environment',
            sa.Enum('production', 'staging', name='deployment_environment'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('draft', 'deploying', 'active', 'failed', 'stopped', name='deployment_status'),
            nullable=False,
        ),
        sa.Column('provider', sa.String(length=32), nullable=True),
        sa.Column('live_url', sa.String(length=1024), nullable=True),
        sa.Column('storage_ref', sa.String(length=1024), nullable=True),
        sa.Column('error', sa.String(length=1024), nullable=True),
        sa.Column('deployed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['website_id'], ['websites.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_deployments_project_id'), 'deployments', ['project_id'], unique=False)
    op.create_index(op.f('ix_deployments_user_id'), 'deployments', ['user_id'], unique=False)
    op.create_index(op.f('ix_deployments_website_id'), 'deployments', ['website_id'], unique=False)
    op.create_index(op.f('ix_deployments_status'), 'deployments', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deployments_status'), table_name='deployments')
    op.drop_index(op.f('ix_deployments_website_id'), table_name='deployments')
    op.drop_index(op.f('ix_deployments_user_id'), table_name='deployments')
    op.drop_index(op.f('ix_deployments_project_id'), table_name='deployments')
    op.drop_table('deployments')
    op.execute("DROP TYPE deployment_status")
    op.execute("DROP TYPE deployment_environment")
