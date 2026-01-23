"""API router for journal features."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.domains.journal.models import (
    JournalEntry,
    Achievement,
    CharacterAchievement,
    WorldLocation,
    WorldConsequence,
    EquipmentHistory,
)
from app.domains.journal.schemas import (
    JournalEntryCreate,
    JournalEntryUpdate,
    JournalEntryResponse,
    AchievementResponse,
    CharacterAchievementResponse,
    WorldLocationCreate,
    WorldLocationUpdate,
    WorldLocationResponse,
    WorldConsequenceCreate,
    WorldConsequenceResponse,
    EquipmentHistoryCreate,
    EquipmentHistoryUpdate,
    EquipmentHistoryResponse,
    SessionSummary,
)
from app.domains.journal.summary_service import SessionSummaryService

router = APIRouter()


# ============ Session Summaries ============

@router.post("/sessions/{session_id}/summarize", response_model=JournalEntryResponse)
async def generate_session_summary(
    session_id: UUID,
    save_to_journal: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Generate an AI summary of a game session."""
    service = SessionSummaryService(db)
    summary_data = await service.generate_session_summary(
        session_id=session_id,
        save_to_journal=save_to_journal,
    )

    if save_to_journal:
        # Return the created journal entry
        result = await db.execute(
            select(JournalEntry)
            .where(JournalEntry.session_id == session_id)
            .where(JournalEntry.entry_type == "auto_summary")
            .order_by(JournalEntry.created_at.desc())
            .limit(1)
        )
        entry = result.scalar_one_or_none()
        if entry:
            return entry

    # If not saving, return a transient response
    raise HTTPException(
        status_code=200,
        detail=summary_data
    )


# ============ Journal Entries ============

@router.get("/entries", response_model=List[JournalEntryResponse])
async def list_journal_entries(
    campaign_id: Optional[UUID] = None,
    character_id: Optional[UUID] = None,
    session_id: Optional[UUID] = None,
    entry_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List journal entries with filtering."""
    query = select(JournalEntry).order_by(JournalEntry.sequence.desc())

    if campaign_id:
        query = query.where(JournalEntry.campaign_id == campaign_id)
    if character_id:
        query = query.where(JournalEntry.character_id == character_id)
    if session_id:
        query = query.where(JournalEntry.session_id == session_id)
    if entry_type:
        query = query.where(JournalEntry.entry_type == entry_type)

    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/entries", response_model=JournalEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_journal_entry(
    entry: JournalEntryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new journal entry (player note)."""
    # Get next sequence number
    result = await db.execute(
        select(func.coalesce(func.max(JournalEntry.sequence), 0))
        .where(JournalEntry.campaign_id == entry.campaign_id)
    )
    next_sequence = result.scalar() + 1

    db_entry = JournalEntry(
        **entry.model_dump(),
        sequence=next_sequence,
    )
    db.add(db_entry)
    await db.flush()
    await db.refresh(db_entry)
    return db_entry


@router.patch("/entries/{entry_id}", response_model=JournalEntryResponse)
async def update_journal_entry(
    entry_id: UUID,
    entry_update: JournalEntryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a journal entry."""
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    update_data = entry_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(entry, field, value)

    await db.flush()
    await db.refresh(entry)
    return entry


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_journal_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a journal entry."""
    result = await db.execute(
        select(JournalEntry).where(JournalEntry.id == entry_id)
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=404, detail="Journal entry not found")

    await db.delete(entry)
    await db.commit()


# ============ Achievements ============

@router.get("/achievements", response_model=List[AchievementResponse])
async def list_achievements(
    db: AsyncSession = Depends(get_db),
):
    """List all available achievements."""
    result = await db.execute(select(Achievement))
    return list(result.scalars().all())


@router.get("/characters/{character_id}/achievements", response_model=List[CharacterAchievementResponse])
async def list_character_achievements(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List achievements earned by a character."""
    result = await db.execute(
        select(CharacterAchievement)
        .options(selectinload(CharacterAchievement.achievement))
        .where(CharacterAchievement.character_id == character_id)
    )
    return list(result.scalars().all())


# ============ World Locations ============

@router.get("/locations", response_model=List[WorldLocationResponse])
async def list_world_locations(
    campaign_id: UUID,
    parent_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
):
    """List world locations for a campaign."""
    query = select(WorldLocation).where(WorldLocation.campaign_id == campaign_id)

    if parent_id:
        query = query.where(WorldLocation.parent_location_id == parent_id)
    else:
        query = query.where(WorldLocation.parent_location_id.is_(None))

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/locations", response_model=WorldLocationResponse, status_code=status.HTTP_201_CREATED)
async def create_world_location(
    location: WorldLocationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new world location."""
    db_location = WorldLocation(**location.model_dump())
    db.add(db_location)
    await db.flush()
    await db.refresh(db_location)
    return db_location


@router.patch("/locations/{location_id}", response_model=WorldLocationResponse)
async def update_world_location(
    location_id: UUID,
    location_update: WorldLocationUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a world location."""
    result = await db.execute(
        select(WorldLocation).where(WorldLocation.id == location_id)
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(status_code=404, detail="Location not found")

    update_data = location_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(location, field, value)

    await db.flush()
    await db.refresh(location)
    return location


# ============ World Consequences ============

@router.get("/consequences", response_model=List[WorldConsequenceResponse])
async def list_world_consequences(
    campaign_id: UUID,
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """List world consequences for a campaign."""
    query = select(WorldConsequence).where(WorldConsequence.campaign_id == campaign_id)

    if active_only:
        query = query.where(WorldConsequence.is_active == True)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/consequences", response_model=WorldConsequenceResponse, status_code=status.HTTP_201_CREATED)
async def create_world_consequence(
    consequence: WorldConsequenceCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new world consequence."""
    db_consequence = WorldConsequence(**consequence.model_dump())
    db.add(db_consequence)
    await db.flush()
    await db.refresh(db_consequence)
    return db_consequence


# ============ Equipment History ============

@router.get("/equipment", response_model=List[EquipmentHistoryResponse])
async def list_equipment_history(
    character_id: UUID,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List equipment history for a character."""
    query = select(EquipmentHistory).where(EquipmentHistory.character_id == character_id)

    if status_filter:
        query = query.where(EquipmentHistory.status == status_filter)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/equipment", response_model=EquipmentHistoryResponse, status_code=status.HTTP_201_CREATED)
async def create_equipment_history(
    equipment: EquipmentHistoryCreate,
    db: AsyncSession = Depends(get_db),
):
    """Record a new equipment item."""
    db_equipment = EquipmentHistory(**equipment.model_dump())
    db.add(db_equipment)
    await db.flush()
    await db.refresh(db_equipment)
    return db_equipment


@router.patch("/equipment/{equipment_id}", response_model=EquipmentHistoryResponse)
async def update_equipment_history(
    equipment_id: UUID,
    equipment_update: EquipmentHistoryUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update equipment status (lost, sold, etc.)."""
    result = await db.execute(
        select(EquipmentHistory).where(EquipmentHistory.id == equipment_id)
    )
    equipment = result.scalar_one_or_none()

    if not equipment:
        raise HTTPException(status_code=404, detail="Equipment not found")

    update_data = equipment_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(equipment, field, value)

    await db.flush()
    await db.refresh(equipment)
    return equipment
