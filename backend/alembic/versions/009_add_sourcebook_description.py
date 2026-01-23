"""Add description column to pdf_documents.

Revision ID: 009
Revises: 008
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add description column to pdf_documents
    op.execute("""
        ALTER TABLE pdf_documents
        ADD COLUMN IF NOT EXISTS description TEXT
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE pdf_documents
        DROP COLUMN IF EXISTS description
    """)
