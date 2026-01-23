from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class NPCType(str, enum.Enum):
    HUMANOID = "humanoid"
    MONSTER = "monster"
    CREATURE = "creature"


class DispositionLevel(str, enum.Enum):
    HOSTILE = "hostile"
    UNFRIENDLY = "unfriendly"
    NEUTRAL = "neutral"
    FRIENDLY = "friendly"
    LOYAL = "loyal"


class NPCDetails(Base, BaseModel):
    """Extended NPC data including personality, disposition, and location."""

    __tablename__ = "npc_details"

    campaign_id = Column(UUID(as_uuid=True), ForeignKey("campaigns.id"), nullable=False)

    name = Column(String(100), nullable=False)
    npc_type = Column(SQLEnum(NPCType), default=NPCType.HUMANOID, nullable=False)

    # Physical description
    description = Column(Text)
    portrait_url = Column(String(500))

    # Personality traits
    personality = Column(JSONB, default={})

    # Current location
    location = Column(String(200))

    # Combat stats (for monsters)
    hit_dice = Column(String(20))
    armor_class = Column(Integer)
    thac0 = Column(Integer)
    morale = Column(Integer)
    attacks = Column(JSONB, default=[])
    special_abilities = Column(JSONB, default=[])

    # Treasure and inventory
    treasure = Column(JSONB, default=[])

    # Is this NPC alive?
    is_alive = Column(Boolean, default=True)

    # Notes
    notes = Column(Text)

    # Relationships
    relationships = relationship("NPCRelationship", back_populates="npc")
    disposition_history = relationship("DispositionHistory", back_populates="npc")


class NPCRelationship(Base, BaseModel):
    """Relationships between NPCs and player characters."""

    __tablename__ = "npc_relationships"

    npc_id = Column(UUID(as_uuid=True), ForeignKey("npc_details.id"), nullable=False)
    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)

    # Current disposition
    disposition = Column(
        SQLEnum(DispositionLevel),
        default=DispositionLevel.NEUTRAL,
        nullable=False,
    )

    # Reaction roll modifier
    reaction_modifier = Column(Integer, default=0)

    # Relationship notes
    notes = Column(Text)

    # Relationships
    npc = relationship("NPCDetails", back_populates="relationships")
    character = relationship("Character", back_populates="npc_relationships")


class DispositionHistory(Base, BaseModel):
    """Track NPC attitude changes over time."""

    __tablename__ = "disposition_history"

    npc_id = Column(UUID(as_uuid=True), ForeignKey("npc_details.id"), nullable=False)
    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=False)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=True)

    from_disposition = Column(SQLEnum(DispositionLevel), nullable=False)
    to_disposition = Column(SQLEnum(DispositionLevel), nullable=False)

    # What caused the change?
    reason = Column(Text)

    # Relationships
    npc = relationship("NPCDetails", back_populates="disposition_history")
