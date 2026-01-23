"""Pydantic schemas for spells."""

from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime


class SpellBase(BaseModel):
    name: str
    code: str
    level: int
    spell_class: str
    duration: Optional[str] = None
    range: Optional[str] = None
    description: str
    reversible: bool = False
    reversed_name: Optional[str] = None
    save: Optional[str] = None
    area_of_effect: Optional[str] = None
    source_book: str = "OSE Basic"


class SpellResponse(SpellBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True


class SpellStatusResponse(BaseModel):
    can_cast: bool
    reason: Optional[str] = None
    spell_class: Optional[str] = None
    max_spell_level: int = 0
    spell_slots: Dict[int, int] = {}
    spells_memorized: Dict[str, List[str]] = {}
    slots_remaining: Dict[int, int] = {}
    spellbook: Optional[List[str]] = None


class MemorizeSpellRequest(BaseModel):
    spell_code: str


class CastSpellRequest(BaseModel):
    spell_code: str


class RestMemorizeRequest(BaseModel):
    spells: List[str]  # List of spell codes to memorize after rest


class AddToSpellbookRequest(BaseModel):
    spell_code: str


class SpellActionResponse(BaseModel):
    success: bool
    message: str
    spell: Optional[SpellResponse] = None
