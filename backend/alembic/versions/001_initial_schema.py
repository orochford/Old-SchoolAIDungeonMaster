"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create rpg_systems table
    op.create_table(
        'rpg_systems',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('code', sa.String(50), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('version', sa.String(50)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('config', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create campaigns table
    op.create_table(
        'campaigns',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('rpg_system_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rpg_systems.id'), nullable=False),
        sa.Column('game_state', postgresql.JSONB, default={}),
        sa.Column('settings', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create characters table
    op.create_table(
        'characters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('rpg_system_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rpg_systems.id'), nullable=False),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id')),
        sa.Column('level', sa.Integer, default=1),
        sa.Column('experience_points', sa.Integer, default=0),
        sa.Column('current_hp', sa.Integer, nullable=False),
        sa.Column('max_hp', sa.Integer, nullable=False),
        sa.Column('attributes', postgresql.JSONB, default={}),
        sa.Column('backstory', sa.Text),
        sa.Column('notes', sa.Text),
        sa.Column('portrait_url', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create character_level_history table
    op.create_table(
        'character_level_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('from_level', sa.Integer, nullable=False),
        sa.Column('to_level', sa.Integer, nullable=False),
        sa.Column('xp_at_level', sa.Integer, nullable=False),
        sa.Column('changes', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create item_templates table
    op.create_table(
        'item_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rpg_system_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rpg_systems.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('category', sa.String(50), nullable=False),
        sa.Column('weight', sa.Numeric(10, 2), default=0),
        sa.Column('base_value_gp', sa.Integer, default=0),
        sa.Column('properties', postgresql.JSONB, default={}),
        sa.Column('is_magical', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create character_inventory table
    op.create_table(
        'character_inventory',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('item_template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('item_templates.id')),
        sa.Column('custom_name', sa.String(100)),
        sa.Column('custom_description', sa.Text),
        sa.Column('custom_properties', postgresql.JSONB, default={}),
        sa.Column('quantity', sa.Integer, default=1),
        sa.Column('is_equipped', sa.Boolean, default=False),
        sa.Column('is_identified', sa.Boolean, default=True),
        sa.Column('container', sa.String(50)),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create npc_details table
    op.create_table(
        'npc_details',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('npc_type', sa.String(20), default='humanoid'),
        sa.Column('description', sa.Text),
        sa.Column('portrait_url', sa.String(500)),
        sa.Column('personality', postgresql.JSONB, default={}),
        sa.Column('location', sa.String(200)),
        sa.Column('hit_dice', sa.String(20)),
        sa.Column('armor_class', sa.Integer),
        sa.Column('thac0', sa.Integer),
        sa.Column('morale', sa.Integer),
        sa.Column('attacks', postgresql.JSONB, default=[]),
        sa.Column('special_abilities', postgresql.JSONB, default=[]),
        sa.Column('treasure', postgresql.JSONB, default=[]),
        sa.Column('is_alive', sa.Boolean, default=True),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create npc_relationships table
    op.create_table(
        'npc_relationships',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('npc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('npc_details.id'), nullable=False),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('disposition', sa.String(20), default='neutral'),
        sa.Column('reaction_modifier', sa.Integer, default=0),
        sa.Column('notes', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create combat_encounters table (without FK to sessions yet)
    op.create_table(
        'combat_encounters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(200)),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('current_round', sa.Integer, default=1),
        sa.Column('current_turn_index', sa.Integer, default=0),
        sa.Column('combat_log', postgresql.JSONB, default=[]),
        sa.Column('environment', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('campaign_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('campaigns.id'), nullable=False),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('title', sa.String(200)),
        sa.Column('status', sa.String(20), default='active'),
        sa.Column('summary', sa.Text),
        sa.Column('game_state', postgresql.JSONB, default={}),
        sa.Column('current_location', sa.String(200)),
        sa.Column('active_combat_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('combat_encounters.id')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Add FK from combat_encounters to sessions
    op.create_foreign_key(
        'fk_combat_encounters_session_id',
        'combat_encounters', 'sessions',
        ['session_id'], ['id']
    )

    # Create conversation_messages table
    op.create_table(
        'conversation_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('sequence', sa.Integer, nullable=False),
        sa.Column('tool_calls', postgresql.JSONB),
        sa.Column('tool_results', postgresql.JSONB),
        sa.Column('extra_data', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create combat_participants table
    op.create_table(
        'combat_participants',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('encounter_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('combat_encounters.id'), nullable=False),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id')),
        sa.Column('npc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('npc_details.id')),
        sa.Column('name', sa.String(100)),
        sa.Column('participant_type', sa.String(20), nullable=False),
        sa.Column('initiative', sa.Integer, nullable=False),
        sa.Column('current_hp', sa.Integer, nullable=False),
        sa.Column('max_hp', sa.Integer, nullable=False),
        sa.Column('armor_class', sa.Integer),
        sa.Column('thac0', sa.Integer),
        sa.Column('morale', sa.Integer),
        sa.Column('morale_broken', sa.Boolean, default=False),
        sa.Column('is_current_turn', sa.Boolean, default=False),
        sa.Column('has_acted', sa.Boolean, default=False),
        sa.Column('stats', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create condition_templates table
    op.create_table(
        'condition_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rpg_system_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rpg_systems.id'), nullable=False),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('effects', postgresql.JSONB, default={}),
        sa.Column('duration_type', sa.String(20)),
        sa.Column('default_duration', sa.Integer),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create active_conditions table
    op.create_table(
        'active_conditions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('participant_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('combat_participants.id'), nullable=False),
        sa.Column('condition_template_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('condition_templates.id')),
        sa.Column('custom_name', sa.String(50)),
        sa.Column('custom_effects', postgresql.JSONB, default={}),
        sa.Column('remaining_rounds', sa.Integer),
        sa.Column('save_type', sa.String(20)),
        sa.Column('source', sa.String(100)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create disposition_history table
    op.create_table(
        'disposition_history',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('npc_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('npc_details.id'), nullable=False),
        sa.Column('character_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('characters.id'), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id')),
        sa.Column('from_disposition', sa.String(20), nullable=False),
        sa.Column('to_disposition', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create pdf_documents table
    op.create_table(
        'pdf_documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('rpg_system_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('rpg_systems.id'), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('original_filename', sa.String(255), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=False),
        sa.Column('file_size', sa.Integer),
        sa.Column('status', sa.String(20), default='pending'),
        sa.Column('processing_error', sa.Text),
        sa.Column('title', sa.String(255)),
        sa.Column('author', sa.String(255)),
        sa.Column('page_count', sa.Integer),
        sa.Column('chunk_count', sa.Integer, default=0),
        sa.Column('category', sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create pdf_chunks table with vector column
    op.create_table(
        'pdf_chunks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('pdf_documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('start_page', sa.Integer),
        sa.Column('end_page', sa.Integer),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('chunk_metadata', postgresql.JSONB, default={}),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Add vector column using raw SQL
    op.execute('ALTER TABLE pdf_chunks ADD COLUMN embedding vector(1536)')

    # Create index for vector similarity search
    op.execute('CREATE INDEX idx_pdf_chunks_embedding ON pdf_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)')

    # Insert default B/X D&D system
    op.execute("""
        INSERT INTO rpg_systems (id, code, name, description, version, is_active, config)
        VALUES (
            gen_random_uuid(),
            'bx-dnd',
            'Basic/Expert D&D (1981)',
            'The classic Moldvay/Cook Basic and Expert D&D rules from 1981',
            '1981',
            true,
            '{}'::jsonb
        )
    """)


def downgrade() -> None:
    op.drop_table('pdf_chunks')
    op.drop_table('pdf_documents')
    op.drop_table('disposition_history')
    op.drop_table('active_conditions')
    op.drop_table('condition_templates')
    op.drop_table('combat_participants')
    op.drop_table('conversation_messages')
    op.drop_constraint('fk_combat_encounters_session_id', 'combat_encounters', type_='foreignkey')
    op.drop_table('sessions')
    op.drop_table('combat_encounters')
    op.drop_table('npc_relationships')
    op.drop_table('npc_details')
    op.drop_table('character_inventory')
    op.drop_table('item_templates')
    op.drop_table('character_level_history')
    op.drop_table('characters')
    op.drop_table('campaigns')
    op.drop_table('rpg_systems')
    op.execute('DROP EXTENSION IF EXISTS vector')
