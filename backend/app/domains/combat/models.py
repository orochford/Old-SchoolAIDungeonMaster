from sqlalchemy import Column, String, Integer, Text, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum

from app.core.database import Base
from app.shared.base_model import BaseModel


class CombatStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    VICTORY = "victory"
    DEFEAT = "defeat"
    FLED = "fled"


class ParticipantType(str, enum.Enum):
    PLAYER = "player"
    NPC = "npc"
    MONSTER = "monster"


class CombatEncounter(Base, BaseModel):
    """Combat session with state and log."""

    __tablename__ = "combat_encounters"

    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)

    name = Column(String(200))
    status = Column(
        SQLEnum(CombatStatus),
        default=CombatStatus.ACTIVE,
        nullable=False,
    )

    current_round = Column(Integer, default=1, nullable=False)
    current_turn_index = Column(Integer, default=0, nullable=False)

    # Combat log (narrative of what happened)
    combat_log = Column(JSONB, default=[])

    # Environmental factors
    environment = Column(JSONB, default={})

    # Relationships
    participants = relationship("CombatParticipant", back_populates="encounter", order_by="CombatParticipant.initiative.desc()")


class CombatParticipant(Base, BaseModel):
    """Combatant in an encounter with initiative, HP, and conditions."""

    __tablename__ = "combat_participants"

    encounter_id = Column(UUID(as_uuid=True), ForeignKey("combat_encounters.id"), nullable=False)

    # Link to character if player
    character_id = Column(UUID(as_uuid=True), ForeignKey("characters.id"), nullable=True)

    # Link to NPC if NPC/monster
    npc_id = Column(UUID(as_uuid=True), ForeignKey("npc_details.id"), nullable=True)

    # For ad-hoc monsters not in NPC table
    name = Column(String(100))
    participant_type = Column(SQLEnum(ParticipantType), nullable=False)

    # Combat stats
    initiative = Column(Integer, nullable=False)
    current_hp = Column(Integer, nullable=False)
    max_hp = Column(Integer, nullable=False)
    armor_class = Column(Integer)
    thac0 = Column(Integer)  # B/X specific

    # Morale (for monsters/NPCs in B/X)
    morale = Column(Integer)
    morale_broken = Column(Boolean, default=False)

    # Is this participant's turn?
    is_current_turn = Column(Boolean, default=False)

    # Has acted this round?
    has_acted = Column(Boolean, default=False)

    # Additional stats
    stats = Column(JSONB, default={})

    # Relationships
    encounter = relationship("CombatEncounter", back_populates="participants")
    character = relationship("Character", back_populates="combat_participations")
    active_conditions = relationship("ActiveCondition", back_populates="participant")


class ConditionTemplate(Base, BaseModel):
    """Status effect definitions."""

    __tablename__ = "condition_templates"

    rpg_system_id = Column(UUID(as_uuid=True), ForeignKey("rpg_systems.id"), nullable=False)

    name = Column(String(50), nullable=False)
    description = Column(Text)

    # Mechanical effects
    effects = Column(JSONB, default={})

    # Does this condition end automatically?
    duration_type = Column(String(20))  # permanent, rounds, save_ends, etc.
    default_duration = Column(Integer)


class ActiveCondition(Base, BaseModel):
    """Currently applied conditions on combatants."""

    __tablename__ = "active_conditions"

    participant_id = Column(UUID(as_uuid=True), ForeignKey("combat_participants.id"), nullable=False)
    condition_template_id = Column(UUID(as_uuid=True), ForeignKey("condition_templates.id"), nullable=True)

    # For ad-hoc conditions
    custom_name = Column(String(50))
    custom_effects = Column(JSONB, default={})

    # Duration tracking
    remaining_rounds = Column(Integer)
    save_type = Column(String(20))  # death_ray, wands, paralysis, breath, spells

    # Source of the condition
    source = Column(String(100))

    # Relationships
    participant = relationship("CombatParticipant", back_populates="active_conditions")
