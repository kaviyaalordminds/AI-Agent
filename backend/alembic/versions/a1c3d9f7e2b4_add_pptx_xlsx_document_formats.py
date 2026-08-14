"""add pptx and xlsx to document_format enum

Revision ID: a1c3d9f7e2b4
Revises: bbf8a81bf16e
Create Date: 2026-08-14 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "a1c3d9f7e2b4"
down_revision = "bbf8a81bf16e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as
    # long as the new value isn't used in the same transaction — which
    # this migration never does, so no autocommit workaround is needed.
    op.execute("ALTER TYPE document_format ADD VALUE IF NOT EXISTS 'pptx'")
    op.execute("ALTER TYPE document_format ADD VALUE IF NOT EXISTS 'xlsx'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Downgrading would require
    # rebuilding the enum type (create new type, migrate column, drop old
    # type) and rewriting any existing pptx/xlsx rows first; since this is
    # a local-development schema with no production data yet, that's
    # intentionally not implemented here rather than risking data loss.
    raise NotImplementedError(
        "Cannot remove enum values in PostgreSQL without rebuilding the type. "
        "Restore from a backup taken before this migration if a downgrade is truly required."
    )
