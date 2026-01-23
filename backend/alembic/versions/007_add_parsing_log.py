"""Add parsing_log column to adventure_modules.

Revision ID: 007
Revises: 006
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add parsing_log column to adventure_modules
    op.execute("""
        ALTER TABLE adventure_modules
        ADD COLUMN IF NOT EXISTS parsing_log JSONB DEFAULT '[]'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE adventure_modules
        DROP COLUMN IF EXISTS parsing_log
    """)
