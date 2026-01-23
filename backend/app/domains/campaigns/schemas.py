from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from enum import Enum


class CampaignStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


# RPG System schemas
class RPGSystemBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    version: Optional[str] = None
    config: Dict[str, Any] = Field(default_factory=dict)


class RPGSystemCreate(RPGSystemBase):
    pass


class RPGSystemResponse(RPGSystemBase):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Campaign schemas
class CampaignBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    rpg_system_id: UUID
    adventure_document_id: Optional[UUID] = None
    game_state: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[CampaignStatus] = None
    adventure_document_id: Optional[UUID] = None
    game_state: Optional[Dict[str, Any]] = None
    settings: Optional[Dict[str, Any]] = None


class CampaignResponse(CampaignBase):
    id: UUID
    status: CampaignStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CampaignWithSystem(CampaignResponse):
    rpg_system: RPGSystemResponse


class SetAdventureRequest(BaseModel):
    """Request to set a campaign's adventure module."""
    adventure_document_id: Optional[UUID] = None
