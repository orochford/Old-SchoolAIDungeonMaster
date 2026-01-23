"""add_color_analysis_to_extracted_images

Revision ID: c57827718236
Revises: 009
Create Date: 2026-01-22 18:07:29.898603

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c57827718236'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add color analysis columns to extracted_images table
    op.add_column('extracted_images', sa.Column('is_color', sa.Boolean(), nullable=True))
    op.add_column('extracted_images', sa.Column('dominant_colors', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('extracted_images', sa.Column('color_palette', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('extracted_images', sa.Column('brightness', sa.Integer(), nullable=True))
    op.add_column('extracted_images', sa.Column('is_full_page', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('extracted_images', 'is_full_page')
    op.drop_column('extracted_images', 'brightness')
    op.drop_column('extracted_images', 'color_palette')
    op.drop_column('extracted_images', 'dominant_colors')
    op.drop_column('extracted_images', 'is_color')
