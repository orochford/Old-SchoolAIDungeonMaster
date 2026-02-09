"""add structured_markdown_path to adventure_modules

Revision ID: g3h4i5j6k7l8
Revises: f7e8d9c0b1a2
Create Date: 2026-02-08 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g3h4i5j6k7l8'
down_revision: Union[str, None] = 'f7e8d9c0b1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add structured_markdown_path column to adventure_modules
    # Stores the path to the structured markdown export built from
    # enriched extraction results (not the raw OCR text)
    op.add_column('adventure_modules', sa.Column('structured_markdown_path', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('adventure_modules', 'structured_markdown_path')
