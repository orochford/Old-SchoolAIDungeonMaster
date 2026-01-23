"""add multipass extraction fields

Revision ID: bc56310aa377
Revises: c134bbbfef47
Create Date: 2026-01-22 21:59:34.644570

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'bc56310aa377'
down_revision: Union[str, None] = 'c134bbbfef47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add multipass extraction fields to adventure_locations
    op.add_column('adventure_locations', sa.Column('dm_guidance', sa.Text(), nullable=True))
    op.add_column('adventure_locations', sa.Column('atmosphere', sa.Text(), nullable=True))
    op.add_column('adventure_locations', sa.Column('sensory_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Add multipass extraction fields to adventure_modules
    op.add_column('adventure_modules', sa.Column('adventure_flow', sa.Text(), nullable=True))
    op.add_column('adventure_modules', sa.Column('critical_path', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('adventure_modules', sa.Column('dm_overview', sa.Text(), nullable=True))


def downgrade() -> None:
    # Remove fields from adventure_modules
    op.drop_column('adventure_modules', 'dm_overview')
    op.drop_column('adventure_modules', 'critical_path')
    op.drop_column('adventure_modules', 'adventure_flow')

    # Remove fields from adventure_locations
    op.drop_column('adventure_locations', 'sensory_details')
    op.drop_column('adventure_locations', 'atmosphere')
    op.drop_column('adventure_locations', 'dm_guidance')
