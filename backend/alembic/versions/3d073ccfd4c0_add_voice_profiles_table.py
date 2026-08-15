"""add voice_profiles table

Revision ID: 3d073ccfd4c0
Revises: 354955ab3d28
Create Date: 2026-08-15 14:39:14.868099

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3d073ccfd4c0'
down_revision: Union[str, None] = '354955ab3d28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: autogenerate also proposed dropping the 6 composite
    # (user_id, sort_column) indexes added in migration 354955ab3d28 —
    # those were created with raw op.create_index() calls with no
    # matching SQLAlchemy Index()/__table_args__ declaration on their
    # models, so autogenerate's model-vs-DB diff sees them as "extra in
    # DB" and offers to remove them. That would undo real, intentional
    # performance work — removed from this migration; only the new
    # table is created here.
    op.create_table('voice_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('provider', sa.String(length=64), nullable=False),
    sa.Column('provider_ref', sa.String(length=255), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_voice_profiles_user_id'), 'voice_profiles', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_voice_profiles_user_id'), table_name='voice_profiles')
    op.drop_table('voice_profiles')
