"""add image_enhancement to generation_job_type and history_entry_type

Revision ID: b7d4e1f9a3c6
Revises: f1c9a2b7e3d4
Create Date: 2026-08-17 10:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d4e1f9a3c6"
down_revision = "f1c9a2b7e3d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as
    # long as the new value isn't used in the same transaction — which
    # this migration never does, so no autocommit workaround is needed
    # (matches a1c3d9f7e2b4's precedent for document_format).
    op.execute("ALTER TYPE generation_job_type ADD VALUE IF NOT EXISTS 'image_enhancement'")
    op.execute("ALTER TYPE history_entry_type ADD VALUE IF NOT EXISTS 'image_enhancement'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Downgrading would require
    # rebuilding both enum types (create new type, migrate columns, drop
    # old type) and rewriting any existing rows of the new types first;
    # since this is a local-development schema with no production data
    # yet, that's intentionally not implemented here rather than risking
    # data loss.
    raise NotImplementedError(
        "Cannot remove enum values in PostgreSQL without rebuilding the type. "
        "Restore from a backup taken before this migration if a downgrade is truly required."
    )
