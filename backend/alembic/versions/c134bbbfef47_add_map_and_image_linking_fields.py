"""Add map and image linking fields

Revision ID: c134bbbfef47
Revises: 0af0c7da7a28
Create Date: 2026-01-22 21:12:35.424984

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c134bbbfef47'
down_revision: Union[str, None] = '0af0c7da7a28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add image/map fields to adventure_locations
    op.add_column('adventure_locations', sa.Column('source_page', sa.Integer(), nullable=True))
    op.add_column('adventure_locations', sa.Column('map_image_id', sa.UUID(), nullable=True))
    op.add_column('adventure_locations', sa.Column('atmosphere_images', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_foreign_key('fk_adventure_locations_map_image', 'adventure_locations', 'extracted_images', ['map_image_id'], ['id'])

    # Add maps/illustrations to adventure_modules
    op.add_column('adventure_modules', sa.Column('maps', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('adventure_modules', sa.Column('illustrations', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    # Remove from adventure_modules
    op.drop_column('adventure_modules', 'illustrations')
    op.drop_column('adventure_modules', 'maps')

    # Remove from adventure_locations
    op.drop_constraint('fk_adventure_locations_map_image', 'adventure_locations', type_='foreignkey')
    op.drop_column('adventure_locations', 'atmosphere_images')
    op.drop_column('adventure_locations', 'map_image_id')
    op.drop_column('adventure_locations', 'source_page')
