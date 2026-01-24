"""add full_markdown_path to adventure_modules

Revision ID: a1b2c3d4e5f6
Revises: bc56310aa377
Create Date: 2026-01-23 16:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bc56310aa377'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add full_markdown_path column to adventure_modules
    # This stores the path to a markdown file containing the full module text
    # for complete LLM reference during gameplay
    op.add_column('adventure_modules', sa.Column('full_markdown_path', sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column('adventure_modules', 'full_markdown_path')
