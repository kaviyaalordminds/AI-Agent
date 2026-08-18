"""add knowledge_syncs table

Revision ID: d9f3a5c7b1e2
Revises: c2a8f6e91d5b
Create Date: 2026-08-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd9f3a5c7b1e2'
down_revision: Union[str, None] = 'c2a8f6e91d5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_syncs',
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('source', sa.String(length=64), nullable=False),
        sa.Column('topic', sa.String(length=255), nullable=False),
        sa.Column(
            'action',
            sa.Enum('created', 'updated', 'skipped', name='knowledge_sync_action'),
            nullable=False,
        ),
        sa.Column('note_path', sa.String(length=1024), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('error', sa.String(length=1024), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_knowledge_syncs_user_id'), 'knowledge_syncs', ['user_id'], unique=False)
    op.create_index(op.f('ix_knowledge_syncs_action'), 'knowledge_syncs', ['action'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_knowledge_syncs_action'), table_name='knowledge_syncs')
    op.drop_index(op.f('ix_knowledge_syncs_user_id'), table_name='knowledge_syncs')
    op.drop_table('knowledge_syncs')
    op.execute("DROP TYPE knowledge_sync_action")
