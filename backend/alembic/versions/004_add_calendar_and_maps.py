"""Add calendar system and dungeon maps

Revision ID: 004
Revises: 003
Create Date: 2026-01-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Default calendar configuration
DEFAULT_CALENDAR_CONFIG = {
    "months": [
        {"name": "Deepwinter", "days": 30},
        {"name": "Thawmoon", "days": 30},
        {"name": "Seedsow", "days": 31},
        {"name": "Rainmoot", "days": 30},
        {"name": "Highsun", "days": 31},
        {"name": "Summertide", "days": 30},
        {"name": "Harvestmoon", "days": 31},
        {"name": "Leaffall", "days": 30},
        {"name": "Frostfall", "days": 30},
        {"name": "Darknight", "days": 31},
        {"name": "Snowmelt", "days": 30},
        {"name": "Yearsend", "days": 30},
    ],
    "moon_cycle_days": 28,
    "seasons": {
        "winter": [1, 2, 11, 12],
        "spring": [3, 4],
        "summer": [5, 6, 7],
        "autumn": [8, 9, 10],
    },
    "hours_per_day": 24,
}


def upgrade() -> None:
    # Campaign Calendars table
    op.create_table(
        'campaign_calendars',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False, unique=True),
        sa.Column('current_day', sa.Integer, nullable=False, server_default='1'),
        sa.Column('current_month', sa.Integer, nullable=False, server_default='1'),
        sa.Column('current_year', sa.Integer, nullable=False, server_default='1'),
        sa.Column('current_hour', sa.Integer, nullable=False, server_default='8'),
        sa.Column('moon_day', sa.Integer, nullable=False, server_default='0'),
        sa.Column('calendar_config', postgresql.JSONB, server_default=sa.text(f"'{str(DEFAULT_CALENDAR_CONFIG).replace(chr(39), chr(39)+chr(39))}'::jsonb")),
        sa.Column('scheduled_events', postgresql.JSONB, server_default='[]'),
        sa.Column('current_weather', sa.String(100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_campaign_calendars_campaign', 'campaign_calendars', ['campaign_id'])

    # Dungeon Maps table
    op.create_table(
        'dungeon_maps',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('world_locations.id'), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('map_data', sa.Text, nullable=False),
        sa.Column('width', sa.Integer, nullable=False),
        sa.Column('height', sa.Integer, nullable=False),
        sa.Column('revealed_cells', postgresql.JSONB, server_default='[]'),
        sa.Column('markers', postgresql.JSONB, server_default='[]'),
        sa.Column('player_x', sa.Integer, nullable=True),
        sa.Column('player_y', sa.Integer, nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_dungeon_maps_campaign', 'dungeon_maps', ['campaign_id'])
    op.create_index('idx_dungeon_maps_location', 'dungeon_maps', ['location_id'])


def downgrade() -> None:
    op.drop_table('dungeon_maps')
    op.drop_table('campaign_calendars')
