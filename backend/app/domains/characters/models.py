from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class CharacterStatus(str, enum.Enum):
    ACTIVE = "active"
    DEAD = "dead"
    RETIRED = "retired"


class Character(Base, BaseModel):
    """Player character with system-agnostic and system-specific attributes."""

    __tablename__ = "characters"

    name = Column(String(100), nullable=False)
    status = Column(
        SQLEnum(CharacterStatus),
        default=CharacterStatus.ACTIVE,
        nullable=False,
    )

    # Foreign keys
    rpg_system_id = Column(UUID(as_uuid=True), ForeignKey("rpg_systems.id"), nullable=False)
    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=True)

    # Core attributes (system-agnostic)
    level = Column(Integer, default=1, nullable=False)
    experience_points = Column(Integer, default=0, nullable=False)
    current_hp = Column(Integer, nullable=False)
    max_hp = Column(Integer, nullable=False)

    # System-specific attributes stored as JSONB
    # For B/X D&D: class, abilities, saving_throws, thac0, etc.
    attributes = Column(JSONB, default={}, nullable=False)

    # Character backstory and notes
    backstory = Column(Text)
    notes = Column(Text)

    # Portrait/avatar URL
    portrait_url = Column(String(500))

    # Relationships
    rpg_system = relationship("RPGSystem", back_populates="characters")
    campaign = relationship("Campaign", back_populates="characters")
    level_history = relationship("CharacterLevelHistory", back_populates="character")
    inventory = relationship("CharacterInventory", back_populates="character")
    npc_relationships = relationship("NPCRelationship", back_populates="character")
    combat_participations = relationship("CombatParticipant", back_populates="character")
    journal_entries = relationship("JournalEntry", back_populates="character")
    achievements = relationship("CharacterAchievement", back_populates="character")
    equipment_history = relationship("EquipmentHistory", back_populates="character")


class CharacterLevelHistory(Base, BaseModel):
    """Track level progression and associated changes."""

    __tablename__ = "character_level_history"

    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)
    from_level = Column(Integer, nullable=False)
    to_level = Column(Integer, nullable=False)
    xp_at_level = Column(Integer, nullable=False)

    # What changed at this level (HP gained, abilities, etc.)
    changes = Column(JSONB, default={})

    # Relationships
    character = relationship("Character", back_populates="level_history")
