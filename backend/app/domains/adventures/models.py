"""Adventure module parsing models for structured data extraction."""

from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class ParsingStatus(str, enum.Enum):
    """Status of adventure module parsing."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class EncounterType(str, enum.Enum):
    """Type of encounter."""
    FIXED = "fixed"
    WANDERING = "wandering"


class AdventureModule(Base, BaseModel):
    """Parsed adventure module with extracted metadata and content."""

    __tablename__ = "adventure_modules"

    # Link to source PDF document
    pdf_document_id = Column(UUID(as_uuid=True), ForeignKey("pdf_documents.id"), nullable=False, unique=True)

    # Module identification
    title = Column(String(255), nullable=False)
    code = Column(String(50))  # e.g., "B4", "X1"

    # Recommended level and party info
    recommended_level_min = Column(Integer)
    recommended_level_max = Column(Integer)
    recommended_party_size_min = Column(Integer)
    recommended_party_size_max = Column(Integer)

    # Module summary/description
    summary = Column(Text)

    # Player-facing background text (read-aloud intro)
    player_background = Column(Text)

    # Path to full module markdown file (for complete LLM reference)
    full_markdown_path = Column(String(512), nullable=True)

    # Rumors table as structured JSON
    # Format: [{"roll": "1-2", "rumor": "...", "is_true": true}, ...]
    rumors_table = Column(JSONB, default=[])

    # Parsing status
    parsing_status = Column(
        SQLEnum(ParsingStatus, name='parsingstatus', create_type=False),
        default=ParsingStatus.PENDING,
        nullable=False,
    )
    parsing_error = Column(Text)
    parsing_progress = Column(Integer, default=0)  # 0-100 progress
    parsing_log = Column(JSONB, default=[])  # List of log messages from parsing

    # Parsing statistics
    location_count = Column(Integer, default=0)
    npc_count = Column(Integer, default=0)
    encounter_count = Column(Integer, default=0)
    item_count = Column(Integer, default=0)

    # Extracted images/maps for this module
    # Format: [{"image_id": "uuid", "image_type": "map", "page": 5, "title": "Level 1 Map"}, ...]
    maps = Column(JSONB, default=[])
    illustrations = Column(JSONB, default=[])

    # Multi-pass extraction: Adventure flow and DM guidance
    adventure_flow = Column(Text)  # Overall narrative description
    critical_path = Column(JSONB, default=[])  # List of must-visit location keys
    dm_overview = Column(Text)  # Module-wide DM guidance

    # Relationships
    pdf_document = relationship("PDFDocument", backref="adventure_module")
    locations = relationship("AdventureLocation", back_populates="module", cascade="all, delete-orphan")
    npcs = relationship("AdventureNPC", back_populates="module", cascade="all, delete-orphan")
    encounters = relationship("AdventureEncounter", back_populates="module", cascade="all, delete-orphan")
    items = relationship("AdventureItem", back_populates="module", cascade="all, delete-orphan")
    story_beats = relationship("AdventureStoryBeat", back_populates="module", cascade="all, delete-orphan")


class AdventureLocation(Base, BaseModel):
    """A keyed location within an adventure module."""

    __tablename__ = "adventure_locations"

    module_id = Column(UUID(as_uuid=True), ForeignKey("adventure_modules.id"), nullable=False)

    # Location identification
    location_key = Column(String(50), nullable=False)  # e.g., "1", "1a", "Area 1"
    name = Column(String(255), nullable=False)

    # Location content
    dm_description = Column(Text, nullable=False)  # Full DM text
    read_aloud_text = Column(Text)  # Player-facing read-aloud description
    source_text = Column(Text)  # Verbatim text from PDF, never modified

    # Room features as JSON list
    # Format: [{"feature": "...", "details": "..."}, ...]
    features = Column(JSONB, default=[])

    # Exits and connections
    # Format: {"north": "Area 2", "secret_door": "Area 3 (Search DC 15)"}
    exits = Column(JSONB, default={})

    # Traps and hazards
    # Format: [{"trigger": "...", "effect": "...", "detection": "...", "disarm": "..."}, ...]
    traps = Column(JSONB, default=[])

    # Hidden elements (secret doors, treasure, etc.)
    # Format: [{"type": "secret_door", "detection": "...", "description": "..."}, ...]
    secrets = Column(JSONB, default=[])

    # Treasure in this location (separate from encounters)
    # Format: [{"item": "...", "value": "...", "location": "..."}, ...]
    treasure = Column(JSONB, default=[])

    # Parent/child relationships for sub-areas
    parent_location_id = Column(UUID(as_uuid=True), ForeignKey("adventure_locations.id"), nullable=True)

    # Tier/level within dungeon (for wandering monster tables)
    dungeon_level = Column(Integer, default=1)
    tier = Column(String(50))  # e.g., "Upper Pyramid", "Deep Caverns"

    # Source page number (for linking to maps/images)
    source_page = Column(Integer)

    # Linked images for this location
    # Map showing this location (by image UUID)
    map_image_id = Column(UUID(as_uuid=True), ForeignKey("extracted_images.id"), nullable=True)
    # Atmosphere/illustration images near this location
    # Format: [{"image_id": "uuid", "relevance": "primary|nearby"}]
    atmosphere_images = Column(JSONB, default=[])

    # Multi-pass extraction: DM guidance and atmosphere
    dm_guidance = Column(Text)  # How to run this room
    atmosphere = Column(Text)  # Mood/tone description
    sensory_details = Column(JSONB, default={})  # {sight, sound, smell, touch, mood}

    # Embedding for semantic search
    embedding = Column(Vector(1536))

    # Relationships
    module = relationship("AdventureModule", back_populates="locations")
    parent_location = relationship("AdventureLocation", remote_side="AdventureLocation.id", backref="sub_locations")
    encounters = relationship("AdventureEncounter", back_populates="location")
    npcs = relationship("AdventureNPC", back_populates="location")
    map_image = relationship("ExtractedImage", foreign_keys=[map_image_id])


class AdventureNPC(Base, BaseModel):
    """An NPC from the adventure module."""

    __tablename__ = "adventure_npcs"

    module_id = Column(UUID(as_uuid=True), ForeignKey("adventure_modules.id"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("adventure_locations.id"), nullable=True)

    # NPC identification
    name = Column(String(255), nullable=False)
    title = Column(String(255))  # e.g., "High Priest of Set"

    # NPC description
    description = Column(Text)
    appearance = Column(Text)

    # Personality and roleplay
    personality = Column(Text)
    motivation = Column(Text)
    goals = Column(JSONB, default=[])  # List of goals/objectives

    # Dialogue hooks for roleplay
    # Format: [{"topic": "...", "response": "...", "condition": "..."}, ...]
    dialogue_hooks = Column(JSONB, default=[])

    # Combat stats (B/X format)
    # Format: {"hd": 3, "hp": 15, "ac": 5, "thac0": 17, "attacks": [...], "damage": [...], "save": "F3", "morale": 8}
    stats = Column(JSONB, default={})

    # Equipment and treasure carried
    equipment = Column(JSONB, default=[])
    treasure = Column(JSONB, default=[])

    # Spells if applicable
    spells = Column(JSONB, default=[])

    # Faction/allegiance
    faction = Column(String(255))

    # Starting disposition toward party
    initial_disposition = Column(String(50), default="neutral")  # hostile, unfriendly, neutral, friendly, helpful

    # Is this a unique/boss NPC?
    is_unique = Column(Boolean, default=True)

    # Embedding for semantic search
    embedding = Column(Vector(1536))

    # Relationships
    module = relationship("AdventureModule", back_populates="npcs")
    location = relationship("AdventureLocation", back_populates="npcs")


class AdventureEncounter(Base, BaseModel):
    """An encounter from the adventure module (fixed or wandering)."""

    __tablename__ = "adventure_encounters"

    module_id = Column(UUID(as_uuid=True), ForeignKey("adventure_modules.id"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("adventure_locations.id"), nullable=True)

    # Encounter type
    encounter_type = Column(
        SQLEnum(EncounterType, name='encountertype', create_type=False),
        default=EncounterType.FIXED,
        nullable=False,
    )

    # For wandering monsters
    wandering_table_name = Column(String(255))  # e.g., "Tier 1 - Upper Pyramid"
    die_roll = Column(String(20))  # e.g., "1d6", "2d6"
    roll_range = Column(String(20))  # e.g., "1-2", "3-4", "5-6"
    check_frequency = Column(String(100))  # e.g., "Every 2 turns, 1-in-6 chance"

    # Encounter name/description
    name = Column(String(255), nullable=False)
    description = Column(Text)

    # Creature information
    # Format: [{"name": "Goblin", "count": "1d6", "hd": 1, "hp": 4, "ac": 6, "thac0": 19,
    #           "attacks": ["1 weapon"], "damage": ["1d6"], "save": "NM", "morale": 7,
    #           "special": ["infravision 60'"]}]
    creatures = Column(JSONB, default=[])

    # Tactics and behavior
    tactics = Column(Text)

    # Treasure for this encounter
    treasure = Column(JSONB, default=[])

    # XP value
    xp_value = Column(Integer)

    # Special conditions or triggers
    trigger_condition = Column(Text)  # What triggers this encounter

    # Embedding for semantic search
    embedding = Column(Vector(1536))

    # Relationships
    module = relationship("AdventureModule", back_populates="encounters")
    location = relationship("AdventureLocation", back_populates="encounters")


class AdventureItem(Base, BaseModel):
    """A notable item from the adventure module."""

    __tablename__ = "adventure_items"

    module_id = Column(UUID(as_uuid=True), ForeignKey("adventure_modules.id"), nullable=False)
    location_id = Column(UUID(as_uuid=True), ForeignKey("adventure_locations.id"), nullable=True)

    # Item identification
    name = Column(String(255), nullable=False)
    item_type = Column(String(50))  # treasure, magic_item, key_item, equipment

    # Item description
    description = Column(Text)

    # Value
    value = Column(String(100))  # e.g., "500 gp", "priceless"

    # Magic item properties
    is_magical = Column(Boolean, default=False)
    magical_properties = Column(Text)
    charges = Column(Integer)

    # Is this a key item for progression?
    is_key_item = Column(Boolean, default=False)

    # Where to find it
    found_at = Column(Text)  # Description of where/how it's found

    # Embedding for semantic search
    embedding = Column(Vector(1536))

    # Relationships
    module = relationship("AdventureModule", back_populates="items")
    location = relationship("AdventureLocation")


class AdventureStoryBeat(Base, BaseModel):
    """Story progression and branching points."""

    __tablename__ = "adventure_story_beats"

    module_id = Column(UUID(as_uuid=True), ForeignKey("adventure_modules.id"), nullable=False)

    # Story beat identification
    name = Column(String(255), nullable=False)
    sequence = Column(Integer, nullable=False)  # Order in story

    # Description of this story beat
    description = Column(Text)

    # Trigger conditions
    # Format: {"type": "location", "value": "Area 10"} or {"type": "item", "value": "Golden Key"}
    trigger = Column(JSONB)

    # Outcomes/branches
    # Format: [{"condition": "...", "next_beat": "...", "consequence": "..."}, ...]
    branches = Column(JSONB, default=[])

    # Related locations
    related_locations = Column(ARRAY(String))

    # Is this a critical path beat?
    is_critical_path = Column(Boolean, default=False)

    # Relationships
    module = relationship("AdventureModule", back_populates="story_beats")
