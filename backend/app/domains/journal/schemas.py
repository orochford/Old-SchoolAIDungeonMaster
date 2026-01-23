"""Pydantic schemas for journal features."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from enum import Enum


class EntryType(str, Enum):
    AUTO_SUMMARY = "auto_summary"
    PLAYER_NOTE = "player_note"
    KEY_EVENT = "key_event"
    LOCATION = "location"
    NPC = "npc"
    COMBAT = "combat"
    LOOT = "loot"
    ACHIEVEMENT = "achievement"


# Journal Entry schemas
class JournalEntryCreate(BaseModel):
    session_id: Optional[UUID] = None
    campaign_id: UUID
    character_id: UUID
    entry_type: EntryType = EntryType.PLAYER_NOTE
    title: str = Field(..., max_length=200)
    content: str
    game_date: Optional[str] = None
    entry_metadata: Dict[str, Any] = {}


class JournalEntryUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    content: Optional[str] = None
    game_date: Optional[str] = None
    entry_metadata: Optional[Dict[str, Any]] = None


class JournalEntryResponse(BaseModel):
    id: UUID
    session_id: Optional[UUID]
    campaign_id: UUID
    character_id: UUID
    entry_type: EntryType
    title: str
    content: str
    sequence: int
    game_date: Optional[str]
    entry_metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Achievement schemas
class AchievementResponse(BaseModel):
    id: UUID
    code: str
    name: str
    description: str
    icon: Optional[str]
    rarity: str
    criteria: Dict[str, Any]

    class Config:
        from_attributes = True


class CharacterAchievementResponse(BaseModel):
    id: UUID
    character_id: UUID
    achievement_id: UUID
    session_id: Optional[UUID]
    context: Optional[str]
    created_at: datetime
    achievement: AchievementResponse

    class Config:
        from_attributes = True


# World Location schemas
class WorldLocationCreate(BaseModel):
    campaign_id: UUID
    name: str = Field(..., max_length=200)
    description: Optional[str] = None
    location_type: Optional[str] = None
    parent_location_id: Optional[UUID] = None
    map_x: Optional[int] = None
    map_y: Optional[int] = None
    notes: Optional[str] = None
    location_metadata: Dict[str, Any] = {}


class WorldLocationUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    location_type: Optional[str] = None
    is_discovered: Optional[bool] = None
    is_cleared: Optional[bool] = None
    notes: Optional[str] = None
    location_metadata: Optional[Dict[str, Any]] = None


class WorldLocationResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    name: str
    description: Optional[str]
    location_type: Optional[str]
    parent_location_id: Optional[UUID]
    map_x: Optional[int]
    map_y: Optional[int]
    is_discovered: bool
    is_cleared: bool
    visit_count: int
    first_visited_session_id: Optional[UUID]
    notes: Optional[str]
    location_metadata: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


# World Consequence schemas
class WorldConsequenceCreate(BaseModel):
    campaign_id: UUID
    session_id: Optional[UUID] = None
    trigger_action: str
    consequence: str
    scope: str = "local"
    is_permanent: bool = True
    affected_locations: List[str] = []
    affected_npcs: List[str] = []
    affected_factions: List[str] = []
    is_known_to_player: bool = True


class WorldConsequenceResponse(BaseModel):
    id: UUID
    campaign_id: UUID
    session_id: Optional[UUID]
    trigger_action: str
    consequence: str
    scope: str
    is_permanent: bool
    expires_at: Optional[datetime]
    affected_locations: List[str]
    affected_npcs: List[str]
    affected_factions: List[str]
    is_active: bool
    is_known_to_player: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Equipment History schemas
class EquipmentHistoryCreate(BaseModel):
    character_id: UUID
    item_name: str = Field(..., max_length=200)
    item_type: Optional[str] = None
    is_magical: bool = False
    obtained_from: Optional[str] = None
    obtained_location: Optional[str] = None
    obtained_session_id: Optional[UUID] = None


class EquipmentHistoryUpdate(BaseModel):
    status: Optional[str] = None
    status_details: Optional[str] = None


class EquipmentHistoryResponse(BaseModel):
    id: UUID
    character_id: UUID
    item_name: str
    item_type: Optional[str]
    is_magical: bool
    obtained_from: Optional[str]
    obtained_location: Optional[str]
    obtained_session_id: Optional[UUID]
    status: str
    status_details: Optional[str]
    history_entries: List[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


# Session Summary (for auto-generation)
class SessionSummary(BaseModel):
    session_id: UUID
    title: str
    summary: str
    key_events: List[str]
    npcs_encountered: List[str]
    locations_visited: List[str]
    combat_count: int
    xp_gained: int
    loot_found: List[Dict[str, Any]]
