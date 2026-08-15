"""add poster/logo/graphic_design to generation_job_type, graphic_design to history_entry_type

Revision ID: 6e2c1a9b4f7d
Revises: 3d073ccfd4c0
Create Date: 2026-08-15 00:00:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "6e2c1a9b4f7d"
down_revision = "3d073ccfd4c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as
    # long as the new value isn't used in the same transaction — which
    # this migration never does, so no autocommit workaround is needed
    # (matches a1c3d9f7e2b4's precedent for document_format).
    op.execute("ALTER TYPE generation_job_type ADD VALUE IF NOT EXISTS 'poster'")
    op.execute("ALTER TYPE generation_job_type ADD VALUE IF NOT EXISTS 'logo'")
    op.execute("ALTER TYPE generation_job_type ADD VALUE IF NOT EXISTS 'graphic_design'")
    # history_entry_type already has 'poster' and 'logo' from the initial
    # Phase 3 migration (fe6de1823544) — only 'graphic_design' is new here.
    op.execute("ALTER TYPE history_entry_type ADD VALUE IF NOT EXISTS 'graphic_design'")


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
