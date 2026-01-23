"""Add spells table

Revision ID: 005
Revises: 004
Create Date: 2024-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'spells',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('code', sa.String(50), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('spell_class', sa.String(20), nullable=False),
        sa.Column('duration', sa.String(100), nullable=True),
        sa.Column('range', sa.String(100), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('reversible', sa.Boolean(), default=False),
        sa.Column('reversed_name', sa.String(100), nullable=True),
        sa.Column('save', sa.String(100), nullable=True),
        sa.Column('area_of_effect', sa.String(100), nullable=True),
        sa.Column('source_book', sa.String(100), default='OSE Basic'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index('ix_spells_code', 'spells', ['code'])
    op.create_index('ix_spells_spell_class', 'spells', ['spell_class'])
    op.create_index('ix_spells_level', 'spells', ['level'])


def downgrade() -> None:
    op.drop_index('ix_spells_level', table_name='spells')
    op.drop_index('ix_spells_spell_class', table_name='spells')
    op.drop_index('ix_spells_code', table_name='spells')
    op.drop_table('spells')
