"""Models for adventure journaling, achievements, world tracking, and dungeon maps."""

from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, DateTime, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB, ENUM as PG_ENUM
from sqlalchemy.orm import relationship
from enum import Enum
import uuid

from app.core.database import Base
from app.shared.base_model import BaseModel


class EntryType(str, Enum):
    """Type of journal entry."""
    AUTO_SUMMARY = "auto_summary"       # AI-generated session summary
    PLAYER_NOTE = "player_note"         # Player's personal notes
    KEY_EVENT = "key_event"             # Significant story event
    LOCATION_DISCOVERY = "location"     # New location found
    NPC_ENCOUNTER = "npc"               # NPC meeting
    COMBAT_RECORD = "combat"            # Combat summary
    LOOT_FOUND = "loot"                 # Treasure/items found
    ACHIEVEMENT = "achievement"         # Achievement unlocked


# PostgreSQL enum type that matches the database
entry_type_enum = PG_ENUM(
    'auto_summary', 'player_note', 'key_event', 'location', 'npc', 'combat', 'loot', 'achievement',
    name='entrytype',
    create_type=False  # Type already exists in database
)


class JournalEntry(Base, BaseModel):
    """A journal entry for tracking adventure progress."""
    __tablename__ = "journal_entries"

    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)

    # Use the PostgreSQL ENUM directly with string values
    entry_type = Column(entry_type_enum, nullable=False, default='auto_summary')
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)

    # For timeline ordering
    sequence = Column(Integer, nullable=False, default=0)
    game_date = Column(String(100), nullable=True)  # In-game date if tracked

    # Metadata for different entry types
    entry_metadata = Column("metadata", JSONB, default={})
    # For auto_summary: {npcs_met: [], locations: [], combat_count: int, xp_gained: int}
    # For achievement: {achievement_id: str, rarity: str}
    # For loot: {items: [{name, value, magic: bool}]}

    # Relationships
    session = relationship("Session", back_populates="journal_entries")
    campaign = relationship("Campaign", back_populates="journal_entries")
    character = relationship("Character", back_populates="journal_entries")


class Achievement(Base, BaseModel):
    """Achievement definitions."""
    __tablename__ = "achievements"

    code = Column(String(50), unique=True, nullable=False)  # e.g., "first_blood", "dragon_slayer"
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=False)
    icon = Column(String(50), nullable=True)  # Icon name/emoji
    rarity = Column(String(20), default="common")  # common, uncommon, rare, legendary

    # Criteria for auto-unlock (JSON)
    criteria = Column(JSONB, default={})
    # Examples:
    # {"type": "combat_kills", "creature": "dragon", "count": 1}
    # {"type": "locations_visited", "count": 10}
    # {"type": "gold_accumulated", "amount": 10000}
    # {"type": "level_reached", "level": 5}


class CharacterAchievement(Base, BaseModel):
    """Achievements earned by a character."""
    __tablename__ = "character_achievements"

    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)
    achievement_id = Column(UUID(as_uuid=True), ForeignKey("achievements.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)

    # Context of how it was earned
    context = Column(Text, nullable=True)  # "Slew Frostbite the White Dragon in the Caves of Chaos"

    # Relationships
    character = relationship("Character", back_populates="achievements")
    achievement = relationship("Achievement")


class WorldLocation(Base, BaseModel):
    """Tracked locations in the game world."""
    __tablename__ = "world_locations"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)

    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    location_type = Column(String(50), nullable=True)  # town, dungeon, wilderness, building, room

    # For map positioning (optional)
    parent_location_id = Column(UUID(as_uuid=True), ForeignKey("world_locations.id"), nullable=True)
    map_x = Column(Integer, nullable=True)
    map_y = Column(Integer, nullable=True)

    # State
    is_discovered = Column(Boolean, default=True)
    is_cleared = Column(Boolean, default=False)  # For dungeons
    visit_count = Column(Integer, default=1)
    first_visited_session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)

    # Notes and metadata
    notes = Column(Text, nullable=True)
    location_metadata = Column("metadata", JSONB, default={})
    # {notable_npcs: [], treasures_found: [], dangers: [], connections: []}

    # Relationships
    campaign = relationship("Campaign", back_populates="world_locations")
    parent = relationship("WorldLocation", remote_side="WorldLocation.id", back_populates="children")
    children = relationship("WorldLocation", back_populates="parent")


class WorldConsequence(Base, BaseModel):
    """Track lasting consequences of player actions."""
    __tablename__ = "world_consequences"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)

    trigger_action = Column(Text, nullable=False)  # What the player did
    consequence = Column(Text, nullable=False)     # What changed in the world

    # Scope and duration
    scope = Column(String(50), default="local")    # local, regional, global
    is_permanent = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)   # For temporary consequences

    # What's affected
    affected_locations = Column(JSONB, default=[])  # List of location IDs
    affected_npcs = Column(JSONB, default=[])       # List of NPC names
    affected_factions = Column(JSONB, default=[])   # List of faction names

    # State
    is_active = Column(Boolean, default=True)
    is_known_to_player = Column(Boolean, default=True)  # Some consequences are hidden

    # Relationships
    campaign = relationship("Campaign", back_populates="consequences")


class EquipmentHistory(Base, BaseModel):
    """Track the story of notable equipment."""
    __tablename__ = "equipment_history"

    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)

    item_name = Column(String(200), nullable=False)
    item_type = Column(String(50), nullable=True)  # weapon, armor, ring, etc.
    is_magical = Column(Boolean, default=False)

    # Origin story
    obtained_from = Column(Text, nullable=True)    # "Looted from the Goblin King"
    obtained_location = Column(String(200), nullable=True)
    obtained_session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)

    # Current status
    status = Column(String(50), default="carried")  # carried, stored, lost, destroyed, sold, given
    status_details = Column(Text, nullable=True)    # "Sold to the blacksmith for 50gp"

    # Notable events involving this item
    history_entries = Column(JSONB, default=[])
    # [{date: str, event: "Used to slay the minotaur", session_id: str}]

    # Relationships
    character = relationship("Character", back_populates="equipment_history")


class DungeonMap(Base, BaseModel):
    """ASCII dungeon map with fog of war."""
    __tablename__ = "dungeon_maps"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("world_locations.id"), nullable=True)

    name = Column(String(200), nullable=False)
    map_data = Column(Text, nullable=False)  # ASCII map content
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)

    # Fog of war state - list of [x, y] coordinates that have been revealed
    revealed_cells = Column(JSONB, default=[])

    # Map markers - [{x, y, symbol, label, type}]
    # type can be: 'treasure', 'danger', 'secret', 'npc', 'entrance', 'exit', etc.
    markers = Column(JSONB, default=[])

    # Player position on map
    player_x = Column(Integer, nullable=True)
    player_y = Column(Integer, nullable=True)

    # Whether this is the currently active map for the campaign
    is_active = Column(Boolean, default=False)

    # Relationships
    campaign = relationship("Campaign", backref="dungeon_maps")
    location = relationship("WorldLocation", backref="maps")
