"""add source_text to adventure_locations

Revision ID: f7e8d9c0b1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-01-23 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7e8d9c0b1a2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add source_text column to adventure_locations
    # This stores the verbatim text from the PDF module, never modified
    # Allows validation that dm_description matches source and provides
    # a reliable source of truth for LLM context
    op.add_column('adventure_locations', sa.Column('source_text', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('adventure_locations', 'source_text')
