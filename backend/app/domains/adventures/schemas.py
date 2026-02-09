"""Pydantic schemas for adventure module parsing."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, field_validator
from uuid import UUID
from datetime import datetime


class AdventureModuleBase(BaseModel):
    """Base schema for adventure modules."""
    title: str
    code: Optional[str] = None
    recommended_level_min: Optional[int] = None
    recommended_level_max: Optional[int] = None
    recommended_party_size_min: Optional[int] = None
    recommended_party_size_max: Optional[int] = None
    summary: Optional[str] = None
    player_background: Optional[str] = None


class AdventureModuleResponse(AdventureModuleBase):
    """Response schema for adventure module."""
    id: UUID
    pdf_document_id: UUID
    parsing_status: str
    parsing_progress: int
    parsing_error: Optional[str] = None
    parsing_log: List[str] = []
    location_count: int
    npc_count: int
    encounter_count: int
    item_count: int
    maps: List[Dict[str, Any]] = []
    illustrations: List[Dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime

    @field_validator('maps', 'illustrations', 'parsing_log', mode='before')
    @classmethod
    def none_to_empty_list(cls, v):
        return v if v is not None else []

    class Config:
        from_attributes = True


class AdventureLocationResponse(BaseModel):
    """Response schema for adventure location."""
    id: UUID
    location_key: str
    name: str
    dm_description: str
    read_aloud_text: Optional[str] = None
    features: List[Dict[str, Any]] = []
    exits: Dict[str, str] = {}
    traps: List[Dict[str, Any]] = []
    secrets: List[Dict[str, Any]] = []
    treasure: List[Dict[str, Any]] = []
    dungeon_level: int = 1
    tier: Optional[str] = None
    parent_location_id: Optional[UUID] = None
    source_page: Optional[int] = None
    map_image_id: Optional[UUID] = None
    atmosphere_images: List[Dict[str, Any]] = []

    class Config:
        from_attributes = True


class AdventureNPCResponse(BaseModel):
    """Response schema for adventure NPC."""
    id: UUID
    name: str
    title: Optional[str] = None
    location_id: Optional[UUID] = None
    description: Optional[str] = None
    appearance: Optional[str] = None
    personality: Optional[str] = None
    motivation: Optional[str] = None
    goals: List[str] = []
    dialogue_hooks: List[Dict[str, Any]] = []
    stats: Dict[str, Any] = {}
    equipment: List[str] = []
    treasure: List[str] = []
    spells: List[str] = []
    faction: Optional[str] = None
    initial_disposition: str = "neutral"
    is_unique: bool = True

    class Config:
        from_attributes = True


class AdventureEncounterResponse(BaseModel):
    """Response schema for adventure encounter."""
    id: UUID
    encounter_type: str
    location_id: Optional[UUID] = None
    wandering_table_name: Optional[str] = None
    die_roll: Optional[str] = None
    roll_range: Optional[str] = None
    check_frequency: Optional[str] = None
    name: str
    description: Optional[str] = None
    creatures: List[Dict[str, Any]] = []
    tactics: Optional[str] = None
    treasure: List[Dict[str, Any]] = []
    xp_value: Optional[int] = None
    trigger_condition: Optional[str] = None

    class Config:
        from_attributes = True


class AdventureItemResponse(BaseModel):
    """Response schema for adventure item."""
    id: UUID
    name: str
    item_type: Optional[str] = None
    location_id: Optional[UUID] = None
    description: Optional[str] = None
    value: Optional[str] = None
    is_magical: bool = False
    magical_properties: Optional[str] = None
    charges: Optional[int] = None
    is_key_item: bool = False
    found_at: Optional[str] = None

    class Config:
        from_attributes = True


class ParseAdventureRequest(BaseModel):
    """Request to parse an adventure module."""
    pass  # No parameters needed, document_id comes from URL


class ParseAdventureResponse(BaseModel):
    """Response after starting adventure parsing."""
    message: str
    module_id: UUID
    status: str


class LocationContextResponse(BaseModel):
    """Rich context for a specific location."""
    location: AdventureLocationResponse
    npcs: List[AdventureNPCResponse] = []
    encounters: List[AdventureEncounterResponse] = []
    items: List[AdventureItemResponse] = []
    connected_locations: List[AdventureLocationResponse] = []


class WanderingEncounterResponse(BaseModel):
    """Wandering encounter table entry."""
    table_name: str
    die_roll: str
    check_frequency: Optional[str] = None
    entries: List[AdventureEncounterResponse] = []


class ModuleValidationResponse(BaseModel):
    """Response for module validation endpoint."""
    module_id: UUID
    title: str
    expected_rooms: int
    extracted_rooms: int
    expected_wandering_tables: int
    extracted_wandering_encounters: int
    extracted_fixed_encounters: int
    issues: List[str] = []
    preprocessing_sections: Dict[str, Any] = {}


class GraphVisualizationNode(BaseModel):
    """A node in the graph visualization."""
    id: str
    key: str
    name: str
    dungeon_level: int = 1
    is_empty: bool = False
    has_creatures: bool = False
    has_items: bool = False
    has_traps: bool = False
    has_secrets: bool = False
    has_npcs: bool = False
    is_entrance: bool = False
    creature_summary: str = ""
    encounter_hd_total: float = 0.0


class GraphVisualizationEdge(BaseModel):
    """An edge in the graph visualization."""
    from_id: str
    to_id: str
    direction: str = ""
    is_secret: bool = False
    is_one_way: bool = False


class GraphValidationReportResponse(BaseModel):
    """Graph completeness validation report."""
    dangling_exits: List[Dict[str, Any]] = []
    orphan_locations: List[Dict[str, Any]] = []
    total_locations: int = 0
    total_connections: int = 0


class GraphVisualizationResponse(BaseModel):
    """Response for graph visualization endpoint."""
    module_id: str
    module_title: str
    nodes: List[GraphVisualizationNode] = []
    edges: List[GraphVisualizationEdge] = []
    validation_report: Optional[GraphValidationReportResponse] = None
