"""add composite user_id+sort-column indexes for list endpoints

Revision ID: 354955ab3d28
Revises: 3bac8ec7a505
Create Date: 2026-08-15 14:04:53.761616

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '354955ab3d28'
down_revision: Union[str, None] = '3bac8ec7a505'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Every one of these tables' list endpoint filters by user_id then
    # orders by the column paired with it here (see app/api/history/
    # router.py, app/api/documents/router.py, app/api/jobs/router.py,
    # app/api/agent/router.py, app/api/knowledge/router.py, app/api/
    # projects/router.py) — each column already has its own single-
    # column index (from the table's original migration), but a plain
    # index on user_id alone still leaves the ORDER BY to an in-memory
    # sort once row counts grow. A composite index matches the query
    # shape exactly, letting Postgres satisfy filter+sort from the index
    # directly. Purely additive (CREATE INDEX), no data change.
    op.create_index("ix_history_entries_user_id_created_at", "history_entries", ["user_id", "created_at"])
    op.create_index("ix_documents_user_id_created_at", "documents", ["user_id", "created_at"])
    op.create_index("ix_generation_jobs_user_id_created_at", "generation_jobs", ["user_id", "created_at"])
    op.create_index("ix_conversations_user_id_updated_at", "conversations", ["user_id", "updated_at"])
    op.create_index("ix_knowledge_analyses_user_id_created_at", "knowledge_analyses", ["user_id", "created_at"])
    op.create_index("ix_projects_user_id_updated_at", "projects", ["user_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_projects_user_id_updated_at", table_name="projects")
    op.drop_index("ix_knowledge_analyses_user_id_created_at", table_name="knowledge_analyses")
    op.drop_index("ix_conversations_user_id_updated_at", table_name="conversations")
    op.drop_index("ix_generation_jobs_user_id_created_at", table_name="generation_jobs")
    op.drop_index("ix_documents_user_id_created_at", table_name="documents")
    op.drop_index("ix_history_entries_user_id_created_at", table_name="history_entries")
