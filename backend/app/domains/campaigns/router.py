from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.domains.campaigns.models import RPGSystem, Campaign, CampaignCalendar
from app.domains.campaigns.schemas import (
    RPGSystemCreate,
    RPGSystemResponse,
    CampaignCreate,
    CampaignUpdate,
    CampaignResponse,
    CampaignWithSystem,
    SetAdventureRequest,
)
from app.domains.sourcebooks.models import PDFDocument

router = APIRouter()


# RPG Systems endpoints
@router.get("/systems", response_model=List[RPGSystemResponse])
async def list_rpg_systems(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """List all RPG systems."""
    query = select(RPGSystem)
    if active_only:
        query = query.where(RPGSystem.is_active == True)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/systems", response_model=RPGSystemResponse, status_code=status.HTTP_201_CREATED)
async def create_rpg_system(
    system_data: RPGSystemCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new RPG system."""
    # Check if code already exists
    result = await db.execute(
        select(RPGSystem).where(RPGSystem.code == system_data.code)
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="RPG system with this code already exists",
        )

    system = RPGSystem(**system_data.model_dump())
    db.add(system)
    await db.flush()
    await db.refresh(system)
    return system


@router.get("/systems/{system_id}", response_model=RPGSystemResponse)
async def get_rpg_system(
    system_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get an RPG system by ID."""
    result = await db.execute(
        select(RPGSystem).where(RPGSystem.id == system_id)
    )
    system = result.scalar_one_or_none()

    if not system:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RPG system not found",
        )

    return system


# Campaign endpoints
@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    campaign_data: CampaignCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new campaign."""
    # Verify RPG system exists
    result = await db.execute(
        select(RPGSystem).where(RPGSystem.id == campaign_data.rpg_system_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="RPG system not found",
        )

    campaign = Campaign(**campaign_data.model_dump())
    db.add(campaign)
    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.get("", response_model=List[CampaignResponse])
async def list_campaigns(
    rpg_system_id: UUID = None,
    status: str = None,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List campaigns with optional filtering."""
    query = select(Campaign)

    if rpg_system_id:
        query = query.where(Campaign.rpg_system_id == rpg_system_id)
    if status:
        query = query.where(Campaign.status == status)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{campaign_id}", response_model=CampaignWithSystem)
async def get_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a campaign by ID with RPG system details."""
    result = await db.execute(
        select(Campaign)
        .options(selectinload(Campaign.rpg_system))
        .where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    return campaign


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: UUID,
    campaign_data: CampaignUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    update_data = campaign_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    await db.flush()
    await db.refresh(campaign)
    return campaign


@router.delete("/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a campaign and all related records."""
    from sqlalchemy import delete as sql_delete, update as sql_update
    from app.domains.sessions.models import Session, ConversationMessage
    from app.domains.journal.models import (
        JournalEntry, WorldLocation, WorldConsequence, DungeonMap,
        CharacterAchievement, EquipmentHistory
    )
    from app.domains.npcs.models import NPCDetails, NPCRelationship, DispositionHistory
    from app.domains.combat.models import CombatEncounter, CombatParticipant, ActiveCondition
    from app.domains.characters.models import Character

    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Get all session IDs for this campaign
    session_result = await db.execute(
        select(Session.id).where(Session.campaign_id == campaign_id)
    )
    session_ids = [row[0] for row in session_result.fetchall()]

    # Get all NPC IDs for this campaign
    npc_result = await db.execute(
        select(NPCDetails.id).where(NPCDetails.campaign_id == campaign_id)
    )
    npc_ids = [row[0] for row in npc_result.fetchall()]

    if session_ids:
        # Get combat encounter IDs for these sessions
        combat_result = await db.execute(
            select(CombatEncounter.id).where(CombatEncounter.session_id.in_(session_ids))
        )
        combat_ids = [row[0] for row in combat_result.fetchall()]

        if combat_ids:
            # Get combat participant IDs
            participant_result = await db.execute(
                select(CombatParticipant.id).where(CombatParticipant.encounter_id.in_(combat_ids))
            )
            participant_ids = [row[0] for row in participant_result.fetchall()]

            # Delete active conditions on participants
            if participant_ids:
                await db.execute(sql_delete(ActiveCondition).where(ActiveCondition.participant_id.in_(participant_ids)))

            # Delete combat participants
            await db.execute(sql_delete(CombatParticipant).where(CombatParticipant.encounter_id.in_(combat_ids)))

        # Clear active_combat_id on sessions (circular FK)
        await db.execute(
            sql_update(Session)
            .where(Session.campaign_id == campaign_id)
            .values(active_combat_id=None)
        )

        # Delete combat encounters
        if combat_ids:
            await db.execute(sql_delete(CombatEncounter).where(CombatEncounter.id.in_(combat_ids)))

        # Delete conversation messages
        await db.execute(sql_delete(ConversationMessage).where(ConversationMessage.session_id.in_(session_ids)))

        # Clear nullable session FKs in other tables
        await db.execute(
            sql_update(CharacterAchievement)
            .where(CharacterAchievement.session_id.in_(session_ids))
            .values(session_id=None)
        )
        await db.execute(
            sql_update(EquipmentHistory)
            .where(EquipmentHistory.obtained_session_id.in_(session_ids))
            .values(obtained_session_id=None)
        )
        await db.execute(
            sql_update(WorldLocation)
            .where(WorldLocation.first_visited_session_id.in_(session_ids))
            .values(first_visited_session_id=None)
        )

    # Delete NPC-related records (they reference npc_details.id)
    if npc_ids:
        await db.execute(sql_delete(NPCRelationship).where(NPCRelationship.npc_id.in_(npc_ids)))
        await db.execute(sql_delete(DispositionHistory).where(DispositionHistory.npc_id.in_(npc_ids)))

    # Delete campaign records - order matters for FK constraints
    # journal_entries before sessions (has session_id FK)
    await db.execute(sql_delete(JournalEntry).where(JournalEntry.campaign_id == campaign_id))
    await db.execute(sql_delete(WorldConsequence).where(WorldConsequence.campaign_id == campaign_id))

    # Now safe to delete sessions
    await db.execute(sql_delete(Session).where(Session.campaign_id == campaign_id))

    # Clear location_id FK before deleting world_locations
    await db.execute(
        sql_update(DungeonMap)
        .where(DungeonMap.campaign_id == campaign_id)
        .values(location_id=None)
    )
    # Clear self-referencing parent_location_id
    await db.execute(
        sql_update(WorldLocation)
        .where(WorldLocation.campaign_id == campaign_id)
        .values(parent_location_id=None)
    )

    await db.execute(sql_delete(DungeonMap).where(DungeonMap.campaign_id == campaign_id))
    await db.execute(sql_delete(WorldLocation).where(WorldLocation.campaign_id == campaign_id))
    await db.execute(sql_delete(NPCDetails).where(NPCDetails.campaign_id == campaign_id))

    # Delete campaign calendar if exists
    await db.execute(sql_delete(CampaignCalendar).where(CampaignCalendar.campaign_id == campaign_id))

    # Clear character campaign references (nullable FK)
    await db.execute(
        sql_update(Character)
        .where(Character.campaign_id == campaign_id)
        .values(campaign_id=None)
    )

    await db.delete(campaign)
    await db.commit()


@router.put("/{campaign_id}/adventure", response_model=CampaignResponse)
async def set_campaign_adventure(
    campaign_id: UUID,
    request: SetAdventureRequest,
    db: AsyncSession = Depends(get_db),
):
    """Set or update the adventure module for a campaign."""
    result = await db.execute(
        select(Campaign).where(Campaign.id == campaign_id)
    )
    campaign = result.scalar_one_or_none()

    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    # Verify adventure document exists if provided
    if request.adventure_document_id:
        doc_result = await db.execute(
            select(PDFDocument).where(PDFDocument.id == request.adventure_document_id)
        )
        adventure_doc = doc_result.scalar_one_or_none()

        if not adventure_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Adventure document not found",
            )

        # Verify it's for the same RPG system
        if adventure_doc.rpg_system_id != campaign.rpg_system_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Adventure document must be for the same RPG system as the campaign",
            )

    campaign.adventure_document_id = request.adventure_document_id
    await db.flush()
    await db.refresh(campaign)
    return campaign
