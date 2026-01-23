from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class CombatStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    VICTORY = "victory"
    DEFEAT = "defeat"
    FLED = "fled"


class ParticipantType(str, Enum):
    PLAYER = "player"
    NPC = "npc"
    MONSTER = "monster"


class CombatEncounterCreate(BaseModel):
    session_id: UUID
    name: Optional[str] = None
    environment: Dict[str, Any] = Field(default_factory=dict)


class CombatEncounterResponse(BaseModel):
    id: UUID
    session_id: UUID
    name: Optional[str]
    status: CombatStatus
    current_round: int
    current_turn_index: int
    combat_log: List[Dict[str, Any]]
    environment: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ParticipantCreate(BaseModel):
    encounter_id: UUID
    character_id: Optional[UUID] = None
    npc_id: Optional[UUID] = None
    name: Optional[str] = None
    participant_type: ParticipantType
    initiative: int
    current_hp: int
    max_hp: int
    armor_class: Optional[int] = None
    thac0: Optional[int] = None
    morale: Optional[int] = None
    stats: Dict[str, Any] = Field(default_factory=dict)


class ParticipantResponse(BaseModel):
    id: UUID
    encounter_id: UUID
    character_id: Optional[UUID]
    npc_id: Optional[UUID]
    name: Optional[str]
    participant_type: ParticipantType
    initiative: int
    current_hp: int
    max_hp: int
    armor_class: Optional[int]
    thac0: Optional[int]
    morale: Optional[int]
    morale_broken: bool
    is_current_turn: bool
    has_acted: bool
    stats: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class ConditionCreate(BaseModel):
    participant_id: UUID
    condition_template_id: Optional[UUID] = None
    custom_name: Optional[str] = None
    custom_effects: Dict[str, Any] = Field(default_factory=dict)
    remaining_rounds: Optional[int] = None
    save_type: Optional[str] = None
    source: Optional[str] = None


class CombatActionRequest(BaseModel):
    """Player combat action."""
    action_type: str  # attack, cast, use_item, move, flee, etc.
    target_id: Optional[UUID] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class CombatActionResult(BaseModel):
    """Result of a combat action."""
    success: bool
    description: str
    rolls: List[Dict[str, Any]] = Field(default_factory=list)
    damage_dealt: Optional[int] = None
    effects_applied: List[str] = Field(default_factory=list)
    state_changes: Dict[str, Any] = Field(default_factory=dict)


class CombatEncounterWithParticipants(CombatEncounterResponse):
    participants: List[ParticipantResponse]
