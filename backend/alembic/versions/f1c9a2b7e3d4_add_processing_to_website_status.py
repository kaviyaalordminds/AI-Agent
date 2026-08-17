"""add processing to website_status enum

Revision ID: f1c9a2b7e3d4
Revises: aed8fdc31b7f
Create Date: 2026-08-17 08:15:00.000000

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "f1c9a2b7e3d4"
down_revision = "aed8fdc31b7f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres 12+ allows ALTER TYPE ... ADD VALUE inside a transaction as
    # long as the new value isn't used in the same transaction — which
    # this migration never does, so no autocommit workaround is needed
    # (matches a1c3d9f7e2b4's precedent for document_format).
    op.execute("ALTER TYPE website_status ADD VALUE IF NOT EXISTS 'processing'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Downgrading would require
    # rebuilding the enum type (create new type, migrate the column, drop
    # old type) and rewriting any existing 'processing' rows first; since
    # this is a local-development schema with no production data yet,
    # that's intentionally not implemented here rather than risking data
    # loss.
    raise NotImplementedError(
        "Cannot remove enum values in PostgreSQL without rebuilding the type. "
        "Restore from a backup taken before this migration if a downgrade is truly required."
    )
