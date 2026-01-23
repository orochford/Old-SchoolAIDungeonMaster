from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List
from uuid import UUID
import logging

from app.core.database import get_db

logger = logging.getLogger(__name__)
from app.domains.characters.models import Character, CharacterLevelHistory
from app.domains.characters.schemas import (
    CharacterCreate,
    CharacterUpdate,
    CharacterResponse,
    LevelUpRequest,
    LevelUpResponse,
    SystemCreationOptions,
)
from app.domains.campaigns.models import RPGSystem, Campaign
from app.domains.sessions.models import Session, ConversationMessage
from app.domains.combat.models import CombatEncounter, CombatParticipant, ActiveCondition
from app.domains.npcs.models import NPCRelationship, DispositionHistory
from app.domains.inventory.models import CharacterInventory

router = APIRouter()


# NOTE: This route must be defined BEFORE /{character_id} routes
# to avoid "systems" being matched as a UUID
@router.get("/systems/{system_code}/options", response_model=SystemCreationOptions)
async def get_system_creation_options(
    system_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Get character creation options for a specific RPG system."""
    result = await db.execute(
        select(RPGSystem).where(RPGSystem.code == system_code)
    )
    system = result.scalar_one_or_none()

    if not system:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RPG system not found",
        )

    # Return B/X D&D options if that's the system
    if system_code == "bx-dnd":
        from app.domains.characters.bx_data import get_bx_creation_options
        return get_bx_creation_options()

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=f"Creation options not implemented for system: {system_code}",
    )


@router.post("", response_model=CharacterResponse, status_code=status.HTTP_201_CREATED)
async def create_character(
    character_data: CharacterCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new character."""
    # Verify RPG system exists
    result = await db.execute(
        select(RPGSystem).where(RPGSystem.id == character_data.rpg_system_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RPG system not found",
        )

    character = Character(**character_data.model_dump())
    db.add(character)
    await db.flush()
    await db.refresh(character)
    return character


@router.get("", response_model=List[CharacterResponse])
async def list_characters(
    campaign_id: UUID = None,
    rpg_system_id: UUID = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List characters with optional filtering."""
    query = select(Character)

    if campaign_id:
        query = query.where(Character.campaign_id == campaign_id)
    if rpg_system_id:
        query = query.where(Character.rpg_system_id == rpg_system_id)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{character_id}", response_model=CharacterResponse)
async def get_character(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a character by ID."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    return character


@router.patch("/{character_id}", response_model=CharacterResponse)
async def update_character(
    character_id: UUID,
    character_data: CharacterUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a character."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    update_data = character_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(character, field, value)

    await db.flush()
    await db.refresh(character)
    return character


@router.delete("/{character_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_character(
    character_id: UUID,
    cascade: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """Delete a character.

    Args:
        character_id: The character's UUID
        cascade: If True, also delete related sessions and campaigns
    """
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    # Check for related sessions
    result = await db.execute(
        select(Session).where(Session.character_id == character_id)
    )
    related_sessions = list(result.scalars().all())

    # Check for related campaigns (where this character is assigned)
    related_campaign_ids = set()
    for session in related_sessions:
        related_campaign_ids.add(session.campaign_id)
    if character.campaign_id:
        related_campaign_ids.add(character.campaign_id)

    if related_sessions and not cascade:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Character has related sessions. Use cascade=true to delete them.",
                "related_sessions": len(related_sessions),
                "related_campaigns": len(related_campaign_ids),
            }
        )

    if cascade:
        try:
            logger.info(f"Starting cascade delete for character {character_id}")

            # Delete in dependency order (deepest dependencies first)

            # 1. Delete conversation messages for related sessions
            for session in related_sessions:
                await db.execute(
                    delete(ConversationMessage).where(ConversationMessage.session_id == session.id)
                )

            # 2. Delete combat encounters and their dependencies for sessions
            for session in related_sessions:
                # Get combat encounters for this session
                result = await db.execute(
                    select(CombatEncounter).where(CombatEncounter.session_id == session.id)
                )
                combats = list(result.scalars().all())
                for combat in combats:
                    # Delete active conditions for participants in this combat
                    result = await db.execute(
                        select(CombatParticipant).where(CombatParticipant.encounter_id == combat.id)
                    )
                    participants = list(result.scalars().all())
                    for participant in participants:
                        await db.execute(
                            delete(ActiveCondition).where(ActiveCondition.participant_id == participant.id)
                        )
                    # Delete combat participants
                    await db.execute(
                        delete(CombatParticipant).where(CombatParticipant.encounter_id == combat.id)
                    )
                    await db.delete(combat)

            # 3. Delete disposition history for this character
            await db.execute(
                delete(DispositionHistory).where(DispositionHistory.character_id == character_id)
            )

            # 4. Delete character-specific records
            await db.execute(
                delete(CharacterLevelHistory).where(CharacterLevelHistory.character_id == character_id)
            )
            await db.execute(
                delete(CharacterInventory).where(CharacterInventory.character_id == character_id)
            )
            await db.execute(
                delete(NPCRelationship).where(NPCRelationship.character_id == character_id)
            )
            # Delete any combat participations for this character (in other combats)
            result = await db.execute(
                select(CombatParticipant).where(CombatParticipant.character_id == character_id)
            )
            char_participations = list(result.scalars().all())
            for participant in char_participations:
                await db.execute(
                    delete(ActiveCondition).where(ActiveCondition.participant_id == participant.id)
                )
            await db.execute(
                delete(CombatParticipant).where(CombatParticipant.character_id == character_id)
            )

            # 5. Delete sessions
            for session in related_sessions:
                await db.delete(session)

            # 6. Delete related campaigns and their remaining sessions
            for campaign_id in related_campaign_ids:
                result = await db.execute(
                    select(Campaign).where(Campaign.id == campaign_id)
                )
                campaign = result.scalar_one_or_none()
                if campaign:
                    # Get any other sessions in this campaign
                    result = await db.execute(
                        select(Session).where(Session.campaign_id == campaign_id)
                    )
                    campaign_sessions = list(result.scalars().all())
                    for cs in campaign_sessions:
                        # Delete conversation messages for these sessions too
                        await db.execute(
                            delete(ConversationMessage).where(ConversationMessage.session_id == cs.id)
                        )
                        # Delete combat data for these sessions
                        result = await db.execute(
                            select(CombatEncounter).where(CombatEncounter.session_id == cs.id)
                        )
                        combats = list(result.scalars().all())
                        for combat in combats:
                            result = await db.execute(
                                select(CombatParticipant).where(CombatParticipant.encounter_id == combat.id)
                            )
                            participants = list(result.scalars().all())
                            for participant in participants:
                                await db.execute(
                                    delete(ActiveCondition).where(ActiveCondition.participant_id == participant.id)
                                )
                            await db.execute(
                                delete(CombatParticipant).where(CombatParticipant.encounter_id == combat.id)
                            )
                            await db.delete(combat)
                        await db.delete(cs)
                    await db.delete(campaign)

            # Flush all the deletes before proceeding
            await db.flush()

        except Exception as e:
            logger.exception(f"Error during cascade delete for character {character_id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Cascade delete failed: {str(e)}"
            )

    await db.delete(character)
    await db.commit()


@router.post("/{character_id}/level-up", response_model=LevelUpResponse)
async def level_up_character(
    character_id: UUID,
    level_up_data: LevelUpRequest,
    db: AsyncSession = Depends(get_db),
):
    """Level up a character."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    if level_up_data.new_level <= character.level:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New level must be higher than current level",
        )

    # Record level history
    level_history = CharacterLevelHistory(
        character_id=character_id,
        from_level=character.level,
        to_level=level_up_data.new_level,
        xp_at_level=character.experience_points,
        changes=level_up_data.changes,
    )
    db.add(level_history)

    # Update character
    character.level = level_up_data.new_level
    character.max_hp += level_up_data.hp_gained
    character.current_hp += level_up_data.hp_gained

    # Apply any attribute changes
    if level_up_data.changes:
        for key, value in level_up_data.changes.items():
            if key in character.attributes:
                character.attributes[key] = value

    await db.flush()
    await db.refresh(character)

    return LevelUpResponse(character=character, changes=level_up_data.changes)
