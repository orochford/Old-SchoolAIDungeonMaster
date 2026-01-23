"""Add journal tables for adventure log, achievements, and world tracking

Revision ID: 003
Revises: 002
Create Date: 2026-01-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create entry_type enum
    entry_type_enum = postgresql.ENUM(
        'auto_summary', 'player_note', 'key_event', 'location', 'npc', 'combat', 'loot', 'achievement',
        name='entrytype',
        create_type=False
    )
    entry_type_enum.create(op.get_bind(), checkfirst=True)

    # Journal Entries table
    op.create_table(
        'journal_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('entry_type', entry_type_enum, nullable=False, server_default='auto_summary'),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('sequence', sa.Integer, nullable=False, server_default='0'),
        sa.Column('game_date', sa.String(100), nullable=True),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_journal_campaign', 'journal_entries', ['campaign_id'])
    op.create_index('idx_journal_character', 'journal_entries', ['character_id'])
    op.create_index('idx_journal_session', 'journal_entries', ['session_id'])

    # Achievements table (definitions)
    op.create_table(
        'achievements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('code', sa.String(50), unique=True, nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text, nullable=False),
        sa.Column('icon', sa.String(50), nullable=True),
        sa.Column('rarity', sa.String(20), server_default='common'),
        sa.Column('criteria', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

    # Character Achievements (earned)
    op.create_table(
        'character_achievements',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('achievement_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('achievements.id'), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=True),
        sa.Column('context', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_char_achievements', 'character_achievements', ['character_id'])

    # World Locations
    op.create_table(
        'world_locations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('location_type', sa.String(50), nullable=True),
        sa.Column('parent_location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('world_locations.id'), nullable=True),
        sa.Column('map_x', sa.Integer, nullable=True),
        sa.Column('map_y', sa.Integer, nullable=True),
        sa.Column('is_discovered', sa.Boolean, server_default='true'),
        sa.Column('is_cleared', sa.Boolean, server_default='false'),
        sa.Column('visit_count', sa.Integer, server_default='1'),
        sa.Column('first_visited_session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('metadata', postgresql.JSONB, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_world_locations_campaign', 'world_locations', ['campaign_id'])

    # World Consequences
    op.create_table(
        'world_consequences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=True),
        sa.Column('trigger_action', sa.Text, nullable=False),
        sa.Column('consequence', sa.Text, nullable=False),
        sa.Column('scope', sa.String(50), server_default='local'),
        sa.Column('is_permanent', sa.Boolean, server_default='true'),
        sa.Column('expires_at', sa.DateTime, nullable=True),
        sa.Column('affected_locations', postgresql.JSONB, server_default='[]'),
        sa.Column('affected_npcs', postgresql.JSONB, server_default='[]'),
        sa.Column('affected_factions', postgresql.JSONB, server_default='[]'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('is_known_to_player', sa.Boolean, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_world_consequences_campaign', 'world_consequences', ['campaign_id'])

    # Equipment History
    op.create_table(
        'equipment_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('item_name', sa.String(200), nullable=False),
        sa.Column('item_type', sa.String(50), nullable=True),
        sa.Column('is_magical', sa.Boolean, server_default='false'),
        sa.Column('obtained_from', sa.Text, nullable=True),
        sa.Column('obtained_location', sa.String(200), nullable=True),
        sa.Column('obtained_session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=True),
        sa.Column('status', sa.String(50), server_default='carried'),
        sa.Column('status_details', sa.Text, nullable=True),
        sa.Column('history_entries', postgresql.JSONB, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('idx_equipment_history_character', 'equipment_history', ['character_id'])

    # Insert some default achievements
    op.execute("""
        INSERT INTO achievements (code, name, description, icon, rarity, criteria) VALUES
        ('first_blood', 'First Blood', 'Defeat your first enemy in combat', '⚔️', 'common', '{"type": "combat_kills", "count": 1}'),
        ('dragon_slayer', 'Dragon Slayer', 'Slay a dragon', '🐉', 'legendary', '{"type": "combat_kills", "creature": "dragon", "count": 1}'),
        ('treasure_hunter', 'Treasure Hunter', 'Find 1000 gold pieces worth of treasure', '💰', 'uncommon', '{"type": "gold_found", "amount": 1000}'),
        ('explorer', 'Explorer', 'Visit 10 different locations', '🗺️', 'uncommon', '{"type": "locations_visited", "count": 10}'),
        ('veteran', 'Veteran', 'Reach level 5', '⭐', 'rare', '{"type": "level_reached", "level": 5}'),
        ('survivor', 'Survivor', 'Survive a near-death experience', '💀', 'uncommon', '{"type": "death_saves", "count": 1}'),
        ('diplomat', 'Diplomat', 'Successfully negotiate with 5 NPCs', '🤝', 'uncommon', '{"type": "successful_negotiations", "count": 5}'),
        ('dungeon_delver', 'Dungeon Delver', 'Clear a dungeon completely', '🏰', 'rare', '{"type": "dungeons_cleared", "count": 1}')
        ON CONFLICT (code) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table('equipment_history')
    op.drop_table('world_consequences')
    op.drop_table('world_locations')
    op.drop_table('character_achievements')
    op.drop_table('achievements')
    op.drop_table('journal_entries')

    # Drop enum
    op.execute('DROP TYPE IF EXISTS entrytype')
