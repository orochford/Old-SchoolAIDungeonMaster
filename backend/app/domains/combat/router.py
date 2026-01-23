from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from typing import List
from uuid import UUID

from app.core.database import get_db
from app.domains.combat.models import CombatEncounter, CombatParticipant, CombatStatus
from app.domains.combat.schemas import (
    CombatEncounterCreate,
    CombatEncounterResponse,
    CombatEncounterWithParticipants,
    ParticipantCreate,
    ParticipantResponse,
    CombatActionRequest,
    CombatActionResult,
)
from app.domains.sessions.models import Session

router = APIRouter()


@router.post("", response_model=CombatEncounterResponse, status_code=status.HTTP_201_CREATED)
async def create_combat_encounter(
    encounter_data: CombatEncounterCreate,
    db: AsyncSession = Depends(get_db),
):
    """Start a new combat encounter."""
    # Verify session exists
    result = await db.execute(
        select(Session).where(Session.id == encounter_data.session_id)
    )
    session = result.scalar_one_or_none()

    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    encounter = CombatEncounter(**encounter_data.model_dump())
    db.add(encounter)
    await db.flush()
    await db.refresh(encounter)

    # Update session's active combat
    session.active_combat_id = encounter.id

    return encounter


@router.get("/{encounter_id}", response_model=CombatEncounterWithParticipants)
async def get_combat_encounter(
    encounter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a combat encounter with participants."""
    result = await db.execute(
        select(CombatEncounter)
        .options(selectinload(CombatEncounter.participants))
        .where(CombatEncounter.id == encounter_id)
    )
    encounter = result.scalar_one_or_none()

    if not encounter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Combat encounter not found",
        )

    return encounter


@router.post("/{encounter_id}/participants", response_model=ParticipantResponse, status_code=status.HTTP_201_CREATED)
async def add_participant(
    encounter_id: UUID,
    participant_data: ParticipantCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a participant to a combat encounter."""
    # Verify encounter exists
    result = await db.execute(
        select(CombatEncounter).where(CombatEncounter.id == encounter_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Combat encounter not found",
        )

    participant = CombatParticipant(**participant_data.model_dump())
    db.add(participant)
    await db.flush()
    await db.refresh(participant)
    return participant


@router.post("/{encounter_id}/action", response_model=CombatActionResult)
async def submit_combat_action(
    encounter_id: UUID,
    action: CombatActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Submit a combat action."""
    result = await db.execute(
        select(CombatEncounter)
        .options(selectinload(CombatEncounter.participants))
        .where(CombatEncounter.id == encounter_id)
    )
    encounter = result.scalar_one_or_none()

    if not encounter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Combat encounter not found",
        )

    if encounter.status != CombatStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Combat is not active",
        )

    # TODO: Process combat action through LLM DM service
    # For now, return a placeholder response
    return CombatActionResult(
        success=True,
        description=f"Action '{action.action_type}' received. Combat processing not yet implemented.",
        rolls=[],
        state_changes={},
    )


@router.post("/{encounter_id}/next-turn", response_model=CombatEncounterWithParticipants)
async def advance_turn(
    encounter_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Advance to the next turn in combat."""
    result = await db.execute(
        select(CombatEncounter)
        .options(selectinload(CombatEncounter.participants))
        .where(CombatEncounter.id == encounter_id)
    )
    encounter = result.scalar_one_or_none()

    if not encounter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Combat encounter not found",
        )

    participants = sorted(encounter.participants, key=lambda p: p.initiative, reverse=True)

    if not participants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No participants in combat",
        )

    # Find current participant and advance
    current_index = encounter.current_turn_index
    next_index = (current_index + 1) % len(participants)

    # If we wrapped around, new round
    if next_index == 0:
        encounter.current_round += 1
        for p in participants:
            p.has_acted = False

    # Update turn markers
    for i, p in enumerate(participants):
        p.is_current_turn = (i == next_index)

    encounter.current_turn_index = next_index

    await db.flush()
    await db.refresh(encounter)
    return encounter


@router.post("/{encounter_id}/end", response_model=CombatEncounterResponse)
async def end_combat(
    encounter_id: UUID,
    outcome: str,  # victory, defeat, fled
    db: AsyncSession = Depends(get_db),
):
    """End a combat encounter."""
    result = await db.execute(
        select(CombatEncounter).where(CombatEncounter.id == encounter_id)
    )
    encounter = result.scalar_one_or_none()

    if not encounter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Combat encounter not found",
        )

    try:
        encounter.status = CombatStatus(outcome)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid combat outcome: {outcome}",
        )

    # Clear active combat from session
    result = await db.execute(
        select(Session).where(Session.active_combat_id == encounter_id)
    )
    session = result.scalar_one_or_none()
    if session:
        session.active_combat_id = None

    await db.flush()
    await db.refresh(encounter)
    return encounter
