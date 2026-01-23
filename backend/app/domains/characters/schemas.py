from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class CharacterStatus(str, Enum):
    ACTIVE = "active"
    DEAD = "dead"
    RETIRED = "retired"


class CharacterBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    rpg_system_id: UUID
    campaign_id: Optional[UUID] = None
    level: int = Field(default=1, ge=1)
    experience_points: int = Field(default=0, ge=0)
    current_hp: int
    max_hp: int = Field(..., ge=1)
    attributes: Dict[str, Any] = Field(default_factory=dict)
    backstory: Optional[str] = None
    notes: Optional[str] = None
    portrait_url: Optional[str] = None


class CharacterCreate(CharacterBase):
    pass


class CharacterUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    campaign_id: Optional[UUID] = None
    level: Optional[int] = Field(None, ge=1)
    experience_points: Optional[int] = Field(None, ge=0)
    current_hp: Optional[int] = None
    max_hp: Optional[int] = Field(None, ge=1)
    attributes: Optional[Dict[str, Any]] = None
    backstory: Optional[str] = None
    notes: Optional[str] = None
    portrait_url: Optional[str] = None
    status: Optional[CharacterStatus] = None


class CharacterResponse(CharacterBase):
    id: UUID
    status: CharacterStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LevelUpRequest(BaseModel):
    new_level: int = Field(..., ge=2)
    hp_gained: int = Field(..., ge=0)
    changes: Dict[str, Any] = Field(default_factory=dict)


class LevelUpResponse(BaseModel):
    character: CharacterResponse
    changes: Dict[str, Any]


# B/X D&D specific schemas
class BXAbilityScores(BaseModel):
    strength: int = Field(..., ge=3, le=18)
    intelligence: int = Field(..., ge=3, le=18)
    wisdom: int = Field(..., ge=3, le=18)
    dexterity: int = Field(..., ge=3, le=18)
    constitution: int = Field(..., ge=3, le=18)
    charisma: int = Field(..., ge=3, le=18)


class BXSavingThrows(BaseModel):
    death_ray_poison: int
    wands: int
    paralysis_stone: int
    breath_attack: int
    spells: int


class BXCharacterAttributes(BaseModel):
    character_class: str
    ability_scores: BXAbilityScores
    saving_throws: BXSavingThrows
    thac0: int
    armor_class: int
    movement_rate: int
    gold: int = 0
    alignment: str
    languages: List[str] = Field(default_factory=list)
    prime_requisite_bonus: int = 0


class SystemCreationOptions(BaseModel):
    system_code: str
    classes: List[Dict[str, Any]]
    equipment: List[Dict[str, Any]]
    spells: Optional[List[Dict[str, Any]]] = None
    alignments: List[str]
