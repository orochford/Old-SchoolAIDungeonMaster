"""API routes for spell management."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.domains.spells.models import Spell
from app.domains.spells.schemas import (
    SpellResponse,
    SpellStatusResponse,
    MemorizeSpellRequest,
    CastSpellRequest,
    RestMemorizeRequest,
    AddToSpellbookRequest,
    SpellActionResponse,
)
from app.domains.spells.spell_service import SpellService
from app.domains.characters.models import Character

router = APIRouter()


@router.get("", response_model=List[SpellResponse])
async def list_spells(
    spell_class: Optional[str] = None,
    level: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all spells with optional filtering."""
    query = select(Spell).order_by(Spell.level, Spell.name)

    if spell_class:
        query = query.where(Spell.spell_class == spell_class)
    if level is not None:
        query = query.where(Spell.level == level)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{spell_code}", response_model=SpellResponse)
async def get_spell(
    spell_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific spell by code."""
    result = await db.execute(
        select(Spell).where(Spell.code == spell_code)
    )
    spell = result.scalar_one_or_none()

    if not spell:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Spell not found",
        )

    return spell


@router.get("/character/{character_id}/status", response_model=SpellStatusResponse)
async def get_character_spell_status(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get spell status for a character (slots, memorized, etc.)."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    return spell_service.get_spell_status(character)


@router.get("/character/{character_id}/available", response_model=List[SpellResponse])
async def get_available_spells(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all spells available to a character's class."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    char_class = character.attributes.get("character_class", "")
    max_level = spell_service.get_max_spell_level(char_class, character.level)

    return await spell_service.get_spells_for_class(char_class, max_level)


@router.post("/character/{character_id}/memorize", response_model=SpellActionResponse)
async def memorize_spell(
    character_id: UUID,
    request: MemorizeSpellRequest,
    db: AsyncSession = Depends(get_db),
):
    """Memorize a spell for the character."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    success, message = await spell_service.memorize_spell(character, request.spell_code)

    if success:
        await db.commit()
        await db.refresh(character)

    return SpellActionResponse(success=success, message=message)


@router.post("/character/{character_id}/forget", response_model=SpellActionResponse)
async def forget_spell(
    character_id: UUID,
    request: MemorizeSpellRequest,
    db: AsyncSession = Depends(get_db),
):
    """Forget a memorized spell."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    success, message = await spell_service.forget_spell(character, request.spell_code)

    if success:
        await db.commit()
        await db.refresh(character)

    return SpellActionResponse(success=success, message=message)


@router.post("/character/{character_id}/cast", response_model=SpellActionResponse)
async def cast_spell(
    character_id: UUID,
    request: CastSpellRequest,
    db: AsyncSession = Depends(get_db),
):
    """Cast a memorized spell."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    success, message, spell = await spell_service.cast_spell(character, request.spell_code)

    if success:
        await db.commit()
        await db.refresh(character)

    spell_response = None
    if spell:
        spell_response = SpellResponse.model_validate(spell)

    return SpellActionResponse(success=success, message=message, spell=spell_response)


@router.post("/character/{character_id}/rest", response_model=SpellActionResponse)
async def rest_and_memorize(
    character_id: UUID,
    request: RestMemorizeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rest and memorize new spells."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    success, message = await spell_service.rest_and_rememorize(character, request.spells)

    if success:
        await db.commit()
        await db.refresh(character)

    return SpellActionResponse(success=success, message=message)


@router.post("/character/{character_id}/spellbook/add", response_model=SpellActionResponse)
async def add_to_spellbook(
    character_id: UUID,
    request: AddToSpellbookRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add a spell to a magic-user's spellbook."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    success, message = await spell_service.add_spell_to_spellbook(character, request.spell_code)

    if success:
        await db.commit()
        await db.refresh(character)

    return SpellActionResponse(success=success, message=message)


@router.get("/character/{character_id}/spellbook", response_model=List[SpellResponse])
async def get_spellbook(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get all spells in a character's spellbook."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    spell_service = SpellService(db)
    spellbook_codes = spell_service.get_spellbook(character)

    if not spellbook_codes:
        return []

    # Fetch all spells in spellbook
    result = await db.execute(
        select(Spell).where(Spell.code.in_(spellbook_codes)).order_by(Spell.level, Spell.name)
    )
    return list(result.scalars().all())
