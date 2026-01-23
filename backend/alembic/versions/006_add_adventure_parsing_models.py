"""Add adventure parsing models.

Revision ID: 006
Revises: 005
Create Date: 2025-01-22

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums using raw SQL
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE parsingstatus AS ENUM ('pending', 'processing', 'completed', 'failed');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    op.execute("""
        DO $$ BEGIN
            CREATE TYPE encountertype AS ENUM ('fixed', 'wandering');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Create adventure_modules table
    op.execute("""
        CREATE TABLE IF NOT EXISTS adventure_modules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

            pdf_document_id UUID NOT NULL UNIQUE REFERENCES pdf_documents(id),

            title VARCHAR(255) NOT NULL,
            code VARCHAR(50),

            recommended_level_min INTEGER,
            recommended_level_max INTEGER,
            recommended_party_size_min INTEGER,
            recommended_party_size_max INTEGER,

            summary TEXT,
            player_background TEXT,
            rumors_table JSONB DEFAULT '[]',

            parsing_status parsingstatus NOT NULL DEFAULT 'pending',
            parsing_error TEXT,
            parsing_progress INTEGER DEFAULT 0,

            location_count INTEGER DEFAULT 0,
            npc_count INTEGER DEFAULT 0,
            encounter_count INTEGER DEFAULT 0,
            item_count INTEGER DEFAULT 0
        )
    """)

    # Create adventure_locations table
    op.execute("""
        CREATE TABLE IF NOT EXISTS adventure_locations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

            module_id UUID NOT NULL REFERENCES adventure_modules(id),
            parent_location_id UUID REFERENCES adventure_locations(id),

            location_key VARCHAR(50) NOT NULL,
            name VARCHAR(255) NOT NULL,

            dm_description TEXT NOT NULL,
            read_aloud_text TEXT,

            features JSONB DEFAULT '[]',
            exits JSONB DEFAULT '{}',
            traps JSONB DEFAULT '[]',
            secrets JSONB DEFAULT '[]',
            treasure JSONB DEFAULT '[]',

            dungeon_level INTEGER DEFAULT 1,
            tier VARCHAR(50),

            embedding vector(1536)
        )
    """)

    # Create adventure_npcs table
    op.execute("""
        CREATE TABLE IF NOT EXISTS adventure_npcs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

            module_id UUID NOT NULL REFERENCES adventure_modules(id),
            location_id UUID REFERENCES adventure_locations(id),

            name VARCHAR(255) NOT NULL,
            title VARCHAR(255),

            description TEXT,
            appearance TEXT,

            personality TEXT,
            motivation TEXT,
            goals JSONB DEFAULT '[]',

            dialogue_hooks JSONB DEFAULT '[]',

            stats JSONB DEFAULT '{}',
            equipment JSONB DEFAULT '[]',
            treasure JSONB DEFAULT '[]',
            spells JSONB DEFAULT '[]',

            faction VARCHAR(255),
            initial_disposition VARCHAR(50) DEFAULT 'neutral',
            is_unique BOOLEAN DEFAULT true,

            embedding vector(1536)
        )
    """)

    # Create adventure_encounters table
    op.execute("""
        CREATE TABLE IF NOT EXISTS adventure_encounters (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

            module_id UUID NOT NULL REFERENCES adventure_modules(id),
            location_id UUID REFERENCES adventure_locations(id),

            encounter_type encountertype NOT NULL DEFAULT 'fixed',

            wandering_table_name VARCHAR(255),
            die_roll VARCHAR(20),
            roll_range VARCHAR(20),
            check_frequency VARCHAR(100),

            name VARCHAR(255) NOT NULL,
            description TEXT,

            creatures JSONB DEFAULT '[]',
            tactics TEXT,
            treasure JSONB DEFAULT '[]',
            xp_value INTEGER,
            trigger_condition TEXT,

            embedding vector(1536)
        )
    """)

    # Create adventure_items table
    op.execute("""
        CREATE TABLE IF NOT EXISTS adventure_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

            module_id UUID NOT NULL REFERENCES adventure_modules(id),
            location_id UUID REFERENCES adventure_locations(id),

            name VARCHAR(255) NOT NULL,
            item_type VARCHAR(50),

            description TEXT,
            value VARCHAR(100),

            is_magical BOOLEAN DEFAULT false,
            magical_properties TEXT,
            charges INTEGER,

            is_key_item BOOLEAN DEFAULT false,
            found_at TEXT,

            embedding vector(1536)
        )
    """)

    # Create adventure_story_beats table
    op.execute("""
        CREATE TABLE IF NOT EXISTS adventure_story_beats (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),

            module_id UUID NOT NULL REFERENCES adventure_modules(id),

            name VARCHAR(255) NOT NULL,
            sequence INTEGER NOT NULL,

            description TEXT,
            trigger JSONB,
            branches JSONB DEFAULT '[]',

            related_locations VARCHAR[],
            is_critical_path BOOLEAN DEFAULT false
        )
    """)

    # Create indexes for performance
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_locations_module_id ON adventure_locations(module_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_locations_location_key ON adventure_locations(location_key)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_npcs_module_id ON adventure_npcs(module_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_npcs_location_id ON adventure_npcs(location_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_encounters_module_id ON adventure_encounters(module_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_encounters_location_id ON adventure_encounters(location_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_encounters_wandering_table ON adventure_encounters(wandering_table_name)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_items_module_id ON adventure_items(module_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_adventure_story_beats_module_id ON adventure_story_beats(module_id)")


def downgrade() -> None:
    # Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_adventure_story_beats_module_id")
    op.execute("DROP INDEX IF EXISTS ix_adventure_items_module_id")
    op.execute("DROP INDEX IF EXISTS ix_adventure_encounters_wandering_table")
    op.execute("DROP INDEX IF EXISTS ix_adventure_encounters_location_id")
    op.execute("DROP INDEX IF EXISTS ix_adventure_encounters_module_id")
    op.execute("DROP INDEX IF EXISTS ix_adventure_npcs_location_id")
    op.execute("DROP INDEX IF EXISTS ix_adventure_npcs_module_id")
    op.execute("DROP INDEX IF EXISTS ix_adventure_locations_location_key")
    op.execute("DROP INDEX IF EXISTS ix_adventure_locations_module_id")

    # Drop tables in reverse order
    op.execute("DROP TABLE IF EXISTS adventure_story_beats CASCADE")
    op.execute("DROP TABLE IF EXISTS adventure_items CASCADE")
    op.execute("DROP TABLE IF EXISTS adventure_encounters CASCADE")
    op.execute("DROP TABLE IF EXISTS adventure_npcs CASCADE")
    op.execute("DROP TABLE IF EXISTS adventure_locations CASCADE")
    op.execute("DROP TABLE IF EXISTS adventure_modules CASCADE")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS encountertype CASCADE")
    op.execute("DROP TYPE IF EXISTS parsingstatus CASCADE")
