from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from typing import List, Optional
from uuid import UUID, uuid4
import logging
import os
import aiofiles

from app.core.database import get_db
from app.config import settings

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


def _build_portrait_prompt(character: "Character") -> str:
    """Build a DALL-E prompt from character attributes and physical description."""
    attrs = character.attributes or {}
    char_class = attrs.get("character_class", "adventurer")
    race = attrs.get("race", "human")
    alignment = attrs.get("alignment", "")
    equipment = attrs.get("equipment", [])
    description = attrs.get("description", {}) or {}
    ability_scores = attrs.get("ability_scores", {}) or {}

    # Physical description details
    sex = description.get("sex", "")
    height = description.get("height", "")
    hair = description.get("hair", "")
    eyes = description.get("eyes", "")
    demeanor = description.get("demeanor", "")
    desc_notes = description.get("notes", "")

    # Build appearance line from physical details
    appearance_parts = []
    if sex:
        appearance_parts.append(sex.lower())
    if height:
        appearance_parts.append(height.lower())
    if hair:
        appearance_parts.append(f"{hair.lower()} hair")
    if eyes:
        appearance_parts.append(f"{eyes.lower()} eyes")
    appearance = ", ".join(appearance_parts)

    # Infer build from ability scores
    build_hints = []
    str_score = ability_scores.get("strength", 10)
    cha_score = ability_scores.get("charisma", 10)
    if isinstance(str_score, int) and str_score >= 16:
        build_hints.append("powerfully built")
    elif isinstance(str_score, int) and str_score <= 6:
        build_hints.append("thin and wiry")
    if isinstance(cha_score, int) and cha_score >= 16:
        build_hints.append("striking features")
    elif isinstance(cha_score, int) and cha_score <= 6:
        build_hints.append("rough-looking")

    notable_items = []
    for item in equipment[:5]:
        if isinstance(item, dict):
            notable_items.append(item.get("name", ""))
        else:
            notable_items.append(str(item))

    lines = [
        "Fantasy RPG character portrait in a classic oil painting style, dramatic lighting:",
        f"A {race} {char_class} named {character.name}.",
    ]
    if appearance:
        lines.append(f"Appearance: {appearance}.")
    if build_hints:
        lines.append(f"Build: {', '.join(build_hints)}.")
    if demeanor:
        lines.append(f"Demeanor: {demeanor}.")
    if desc_notes:
        lines.append(desc_notes[:120] + "." if not desc_notes.endswith(".") else desc_notes[:120])
    if alignment:
        lines.append(f"Alignment: {alignment}.")
    if notable_items:
        lines.append(f"Notable equipment: {', '.join(notable_items)}.")
    lines.append("Portrait should be head and shoulders, facing slightly to the side, with a dark moody background.")
    lines.append("Style: Classic fantasy art, detailed, painterly, reminiscent of Larry Elmore or Keith Parkinson.")

    return "\n".join(lines)


async def _generate_portrait_background(character_id: UUID) -> None:
    """Background task to auto-generate a portrait after character creation."""
    from app.core.database import AsyncSessionLocal

    if not settings.openai_api_key:
        logger.info(f"Skipping portrait generation for {character_id}: no OpenAI key")
        return

    async with AsyncSessionLocal() as db:
        try:
            import openai
            import httpx

            result = await db.execute(
                select(Character).where(Character.id == character_id)
            )
            character = result.scalar_one_or_none()
            if not character:
                return

            # Skip if already has a portrait
            if character.portrait_url:
                return

            prompt = _build_portrait_prompt(character)
            logger.info(f"Auto-generating portrait for {character.name} ({character_id})")

            client = openai.OpenAI(api_key=settings.openai_api_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )

            image_url = response.data[0].url

            async with httpx.AsyncClient() as http_client:
                img_response = await http_client.get(image_url)
                img_response.raise_for_status()

                os.makedirs(settings.portraits_storage_path, exist_ok=True)
                filename = f"{character_id}_{uuid4().hex[:8]}.png"
                file_path = os.path.join(settings.portraits_storage_path, filename)

                async with aiofiles.open(file_path, "wb") as out_file:
                    await out_file.write(img_response.content)

                character.portrait_url = f"/api/v1/characters/{character_id}/portrait/{filename}"
                await db.commit()
                logger.info(f"Portrait generated for {character.name}: {filename}")

        except Exception as e:
            logger.error(f"Auto portrait generation failed for {character_id}: {e}")


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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Create a new character and auto-generate a portrait."""
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

    # Auto-generate portrait in background
    background_tasks.add_task(_generate_portrait_background, character.id)

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


@router.post("/{character_id}/portrait/upload")
async def upload_portrait(
    character_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a portrait image for a character."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/gif"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed: {', '.join(allowed_types)}",
        )

    # Create portraits directory if it doesn't exist
    os.makedirs(settings.portraits_storage_path, exist_ok=True)

    # Generate filename
    ext = file.filename.split(".")[-1] if "." in file.filename else "png"
    filename = f"{character_id}_{uuid4().hex[:8]}.{ext}"
    file_path = os.path.join(settings.portraits_storage_path, filename)

    # Delete old portrait file if exists
    if character.portrait_url and character.portrait_url.startswith("/api/v1/characters/"):
        old_filename = character.portrait_url.split("/")[-1]
        old_path = os.path.join(settings.portraits_storage_path, old_filename)
        if os.path.exists(old_path):
            os.remove(old_path)

    # Save file
    async with aiofiles.open(file_path, "wb") as out_file:
        content = await file.read()
        await out_file.write(content)

    # Update character portrait_url
    character.portrait_url = f"/api/v1/characters/{character_id}/portrait/{filename}"
    await db.flush()
    await db.refresh(character)

    return {"portrait_url": character.portrait_url}


@router.get("/{character_id}/portrait/{filename}")
async def get_portrait(
    character_id: UUID,
    filename: str,
):
    """Serve a character portrait image."""
    file_path = os.path.join(settings.portraits_storage_path, filename)

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Portrait not found",
        )

    return FileResponse(file_path)


@router.post("/{character_id}/portrait/preview-prompt")
async def preview_portrait_prompt(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Return the auto-generated DALL-E prompt for review before generating."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    prompt = _build_portrait_prompt(character)
    return {"prompt": prompt}


@router.post("/{character_id}/portrait/generate")
async def generate_portrait(
    character_id: UUID,
    body: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
):
    """Generate a portrait image for a character using AI.

    Accepts optional JSON body with 'prompt' field to use a custom prompt.
    If not provided, auto-generates from character attributes.
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

    if not settings.openai_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Image generation requires OpenAI API key",
        )

    # Use custom prompt if provided, otherwise auto-generate
    prompt = (body or {}).get("prompt") or _build_portrait_prompt(character)

    try:
        import openai

        client = openai.OpenAI(api_key=settings.openai_api_key)
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url

        # Download and save the image
        import httpx
        async with httpx.AsyncClient() as http_client:
            img_response = await http_client.get(image_url)
            img_response.raise_for_status()

            os.makedirs(settings.portraits_storage_path, exist_ok=True)
            filename = f"{character_id}_{uuid4().hex[:8]}.png"
            file_path = os.path.join(settings.portraits_storage_path, filename)

            # Delete old portrait file if exists
            if character.portrait_url and character.portrait_url.startswith("/api/v1/characters/"):
                old_filename = character.portrait_url.split("/")[-1]
                old_path = os.path.join(settings.portraits_storage_path, old_filename)
                if os.path.exists(old_path):
                    os.remove(old_path)

            async with aiofiles.open(file_path, "wb") as out_file:
                await out_file.write(img_response.content)

            # Update character portrait_url
            character.portrait_url = f"/api/v1/characters/{character_id}/portrait/{filename}"
            await db.flush()
            await db.refresh(character)

            return {"portrait_url": character.portrait_url, "prompt": prompt}

    except openai.OpenAIError as e:
        logger.error(f"OpenAI image generation failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Image generation failed: {str(e)}",
        )
    except Exception as e:
        logger.exception(f"Portrait generation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Portrait generation failed: {str(e)}",
        )


@router.delete("/{character_id}/portrait")
async def delete_portrait(
    character_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a character's portrait."""
    result = await db.execute(
        select(Character).where(Character.id == character_id)
    )
    character = result.scalar_one_or_none()

    if not character:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Character not found",
        )

    if character.portrait_url and character.portrait_url.startswith("/api/v1/characters/"):
        filename = character.portrait_url.split("/")[-1]
        file_path = os.path.join(settings.portraits_storage_path, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

    character.portrait_url = None
    await db.flush()
    await db.refresh(character)

    return {"message": "Portrait deleted"}
