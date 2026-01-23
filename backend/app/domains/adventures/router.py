"""API router for adventure module parsing and retrieval."""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.domains.sourcebooks.models import PDFDocument
from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, AdventureItem, ParsingStatus, EncounterType,
)
from app.domains.adventures.schemas import (
    AdventureModuleResponse,
    AdventureLocationResponse,
    AdventureNPCResponse,
    AdventureEncounterResponse,
    AdventureItemResponse,
    ParseAdventureResponse,
    LocationContextResponse,
    WanderingEncounterResponse,
    ModuleValidationResponse,
)

router = APIRouter()


async def parse_adventure_background(document_id: UUID):
    """Background task to parse an adventure module using multi-pass extraction."""
    import logging
    from app.core.database import AsyncSessionLocal
    from app.domains.adventures.multipass_parser import MultiPassParser

    logger = logging.getLogger(__name__)
    parser = None

    async with AsyncSessionLocal() as db:
        try:
            logger.info(f"Starting multi-pass adventure parsing for document {document_id}")
            parser = MultiPassParser(db)
            module = await parser.parse_adventure(document_id)

            # Save the parsing log
            module.parsing_log = parser.parsing_log

            await db.commit()
            logger.info(f"Successfully parsed adventure document {document_id}")
        except Exception as e:
            logger.exception(f"Failed to parse adventure document {document_id}")
            await db.rollback()

            # Update status to failed with a clean error message
            result = await db.execute(
                select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
            )
            module = result.scalar_one_or_none()
            if module:
                module.parsing_status = ParsingStatus.FAILED

                # Clean up the error message - don't expose raw JSON parsing errors
                error_msg = str(e)
                if "JSONDecodeError" in error_msg or "json" in error_msg.lower():
                    error_msg = "Failed to parse LLM response. The document may have unusual formatting."
                elif len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                module.parsing_error = error_msg

                # Save the parsing log even on failure
                if parser:
                    parser._log(f"ERROR: {error_msg}")
                    module.parsing_log = parser.parsing_log

                await db.commit()


@router.post("/{document_id}/parse", response_model=ParseAdventureResponse)
async def parse_adventure(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Trigger LLM parsing of a PDF adventure module.

    This creates structured data from the PDF that can be queried directly.
    """
    # Verify document exists
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Check if already being parsed
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
    )
    existing = result.scalar_one_or_none()

    if existing and existing.parsing_status == ParsingStatus.PROCESSING:
        return ParseAdventureResponse(
            message="Parsing already in progress",
            module_id=existing.id,
            status="processing",
        )

    # Create or update module record
    if existing:
        existing.parsing_status = ParsingStatus.PENDING
        existing.parsing_error = None
        existing.parsing_progress = 0
        module_id = existing.id
    else:
        module = AdventureModule(
            pdf_document_id=document_id,
            title=document.title or document.original_filename,
            parsing_status=ParsingStatus.PENDING,
        )
        db.add(module)
        await db.flush()
        module_id = module.id

    await db.commit()

    # Start background parsing
    background_tasks.add_task(parse_adventure_background, document_id)

    return ParseAdventureResponse(
        message="Parsing started",
        module_id=module_id,
        status="pending",
    )


async def regenerate_embeddings_background(document_id: UUID):
    """Background task to regenerate embeddings only."""
    import logging
    from app.core.database import AsyncSessionLocal
    from app.domains.adventures.multipass_parser import MultiPassParser

    logger = logging.getLogger(__name__)

    async with AsyncSessionLocal() as db:
        try:
            logger.info(f"Regenerating embeddings for document {document_id}")
            parser = MultiPassParser(db)
            module = await parser.parse_adventure(document_id, embeddings_only=True)
            module.parsing_log = parser.parsing_log
            await db.commit()
            logger.info(f"Successfully regenerated embeddings for document {document_id}")
        except Exception as e:
            logger.exception(f"Failed to regenerate embeddings for document {document_id}")
            await db.rollback()

            result = await db.execute(
                select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
            )
            module = result.scalar_one_or_none()
            if module:
                module.parsing_status = ParsingStatus.FAILED
                module.parsing_error = str(e)[:200]
                await db.commit()


@router.post("/{document_id}/embeddings", response_model=ParseAdventureResponse)
async def regenerate_embeddings(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Regenerate embeddings for an already-parsed adventure module.

    Use this if parsing succeeded but embeddings failed - avoids re-running
    expensive LLM extraction.
    """
    # Verify module exists and has data
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
    )
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No parsed module found for this document. Run full parse first.",
        )

    if module.parsing_status == ParsingStatus.PROCESSING:
        return ParseAdventureResponse(
            message="Already processing",
            module_id=module.id,
            status="processing",
        )

    # Update status
    module.parsing_status = ParsingStatus.PENDING
    module.parsing_error = None
    module.parsing_progress = 90
    await db.commit()

    # Start background task
    background_tasks.add_task(regenerate_embeddings_background, document_id)

    return ParseAdventureResponse(
        message="Embeddings regeneration started",
        module_id=module.id,
        status="pending",
    )


@router.get("/{module_id}", response_model=AdventureModuleResponse)
async def get_adventure_module(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a parsed adventure module by ID."""
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    return module


@router.get("/by-document/{document_id}", response_model=AdventureModuleResponse)
async def get_adventure_by_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a parsed adventure module by its source document ID."""
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
    )
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found for this document",
        )

    return module


@router.get("/{module_id}/locations", response_model=List[AdventureLocationResponse])
async def list_locations(
    module_id: UUID,
    tier: Optional[str] = None,
    dungeon_level: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all locations in an adventure module."""
    query = select(AdventureLocation).where(AdventureLocation.module_id == module_id)

    if tier:
        query = query.where(AdventureLocation.tier == tier)
    if dungeon_level:
        query = query.where(AdventureLocation.dungeon_level == dungeon_level)

    query = query.order_by(AdventureLocation.location_key)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{module_id}/locations/{location_key}", response_model=LocationContextResponse)
async def get_location_context(
    module_id: UUID,
    location_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Get rich context for a specific location including NPCs, encounters, and items."""
    # Get the location
    result = await db.execute(
        select(AdventureLocation)
        .where(AdventureLocation.module_id == module_id)
        .where(AdventureLocation.location_key == location_key)
    )
    location = result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_key} not found",
        )

    # Get NPCs at this location
    result = await db.execute(
        select(AdventureNPC).where(AdventureNPC.location_id == location.id)
    )
    npcs = list(result.scalars().all())

    # Get encounters at this location
    result = await db.execute(
        select(AdventureEncounter).where(AdventureEncounter.location_id == location.id)
    )
    encounters = list(result.scalars().all())

    # Get items at this location
    result = await db.execute(
        select(AdventureItem).where(AdventureItem.location_id == location.id)
    )
    items = list(result.scalars().all())

    # Get connected locations from exits
    connected_locations = []
    if location.exits:
        for exit_dest in location.exits.values():
            # Extract location key from exit text (e.g., "Area 2" -> "Area 2")
            dest_key = exit_dest.split("(")[0].strip()
            result = await db.execute(
                select(AdventureLocation)
                .where(AdventureLocation.module_id == module_id)
                .where(AdventureLocation.location_key == dest_key)
            )
            connected = result.scalar_one_or_none()
            if connected:
                connected_locations.append(connected)

    return LocationContextResponse(
        location=location,
        npcs=npcs,
        encounters=encounters,
        items=items,
        connected_locations=connected_locations,
    )


@router.get("/{module_id}/npcs", response_model=List[AdventureNPCResponse])
async def list_npcs(
    module_id: UUID,
    faction: Optional[str] = None,
    is_unique: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all NPCs in an adventure module."""
    query = select(AdventureNPC).where(AdventureNPC.module_id == module_id)

    if faction:
        query = query.where(AdventureNPC.faction == faction)
    if is_unique is not None:
        query = query.where(AdventureNPC.is_unique == is_unique)

    query = query.order_by(AdventureNPC.name)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{module_id}/npcs/{npc_id}", response_model=AdventureNPCResponse)
async def get_npc(
    module_id: UUID,
    npc_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a specific NPC by ID."""
    result = await db.execute(
        select(AdventureNPC)
        .where(AdventureNPC.module_id == module_id)
        .where(AdventureNPC.id == npc_id)
    )
    npc = result.scalar_one_or_none()

    if not npc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="NPC not found",
        )

    return npc


@router.get("/{module_id}/encounters", response_model=List[AdventureEncounterResponse])
async def list_encounters(
    module_id: UUID,
    encounter_type: Optional[str] = None,
    wandering_table_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all encounters in an adventure module."""
    query = select(AdventureEncounter).where(AdventureEncounter.module_id == module_id)

    if encounter_type:
        enc_type = EncounterType.WANDERING if encounter_type == "wandering" else EncounterType.FIXED
        query = query.where(AdventureEncounter.encounter_type == enc_type)
    if wandering_table_name:
        query = query.where(AdventureEncounter.wandering_table_name == wandering_table_name)

    query = query.order_by(AdventureEncounter.name)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{module_id}/wandering-tables", response_model=List[WanderingEncounterResponse])
async def list_wandering_tables(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """List all wandering monster tables in an adventure module."""
    # Get all wandering encounters grouped by table name
    result = await db.execute(
        select(AdventureEncounter)
        .where(AdventureEncounter.module_id == module_id)
        .where(AdventureEncounter.encounter_type == EncounterType.WANDERING)
        .order_by(AdventureEncounter.wandering_table_name, AdventureEncounter.roll_range)
    )
    encounters = list(result.scalars().all())

    # Group by table name
    tables = {}
    for enc in encounters:
        table_name = enc.wandering_table_name or "Default"
        if table_name not in tables:
            tables[table_name] = {
                "table_name": table_name,
                "die_roll": enc.die_roll or "1d6",
                "check_frequency": enc.check_frequency,
                "entries": [],
            }
        tables[table_name]["entries"].append(enc)

    return list(tables.values())


@router.get("/{module_id}/items", response_model=List[AdventureItemResponse])
async def list_items(
    module_id: UUID,
    is_magical: Optional[bool] = None,
    is_key_item: Optional[bool] = None,
    item_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all items in an adventure module."""
    query = select(AdventureItem).where(AdventureItem.module_id == module_id)

    if is_magical is not None:
        query = query.where(AdventureItem.is_magical == is_magical)
    if is_key_item is not None:
        query = query.where(AdventureItem.is_key_item == is_key_item)
    if item_type:
        query = query.where(AdventureItem.item_type == item_type)

    query = query.order_by(AdventureItem.name)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{module_id}/validation", response_model=ModuleValidationResponse)
async def validate_module(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Validate extracted data against document preprocessing.

    Re-runs the preprocessor to compare expected vs actual extraction results.
    Useful for debugging extraction quality.
    """
    import os
    from app.domains.adventures.preprocessor import AdventurePreprocessor

    # Get the module
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Get the source document
    result = await db.execute(
        select(PDFDocument).where(PDFDocument.id == module.pdf_document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source document not found",
        )

    # Get document text
    markdown_content = ""
    if document.markdown_path and os.path.exists(document.markdown_path):
        with open(document.markdown_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()

    # Run preprocessor
    preprocessor = AdventurePreprocessor()
    preprocessed = preprocessor.preprocess(markdown_content) if markdown_content else {'rooms': [], 'wandering_tables': [], 'sections': {}}

    # Count extracted encounters by type
    result = await db.execute(
        select(AdventureEncounter)
        .where(AdventureEncounter.module_id == module_id)
    )
    encounters = list(result.scalars().all())
    wandering_count = sum(1 for e in encounters if e.encounter_type == EncounterType.WANDERING)
    fixed_count = len(encounters) - wandering_count

    # Identify issues
    issues = []
    expected_rooms = len(preprocessed['rooms'])
    expected_wandering = sum(len(t.get('entries', [])) for t in preprocessed['wandering_tables'])

    if module.location_count < expected_rooms * 0.8:
        issues.append(f"Low room extraction: {module.location_count} extracted vs {expected_rooms} expected")

    if module.location_count == 0 and expected_rooms > 0:
        issues.append(f"No rooms extracted (expected {expected_rooms})")

    if wandering_count == 0 and expected_wandering > 0:
        issues.append(f"No wandering encounters extracted (expected ~{expected_wandering})")

    if module.encounter_count == 0:
        issues.append("No encounters extracted at all")

    # Simplify sections for response
    sections_summary = {
        name: {'start': start, 'end': end, 'length': end - start}
        for name, (start, end) in preprocessed['sections'].items()
    }

    return ModuleValidationResponse(
        module_id=module.id,
        title=module.title,
        expected_rooms=expected_rooms,
        extracted_rooms=module.location_count,
        expected_wandering_tables=len(preprocessed['wandering_tables']),
        extracted_wandering_encounters=wandering_count,
        extracted_fixed_encounters=fixed_count,
        issues=issues,
        preprocessing_sections=sections_summary,
    )


@router.get("/{module_id}/images")
async def get_module_images(
    module_id: UUID,
    image_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all extracted images (maps, illustrations) for an adventure module.

    Args:
        module_id: The adventure module UUID
        image_type: Optional filter - 'map', 'illustration', 'cover', or 'all'

    Returns:
        Dict with maps and illustrations arrays, plus image details
    """
    from app.domains.sourcebooks.models import ExtractedImage

    # Get the module
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()

    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Get all images for this document
    query = select(ExtractedImage).where(
        ExtractedImage.document_id == module.pdf_document_id
    )

    if image_type and image_type != 'all':
        query = query.where(ExtractedImage.image_type == image_type)

    query = query.order_by(ExtractedImage.page_number)
    result = await db.execute(query)
    images = list(result.scalars().all())

    # Format response
    return {
        "module_id": module_id,
        "module_title": module.title,
        "total_images": len(images),
        "maps": module.maps or [],
        "illustrations": module.illustrations or [],
        "images": [
            {
                "id": str(img.id),
                "image_type": img.image_type,
                "page_number": img.page_number,
                "title": img.title,
                "path": img.image_path,
                "width": img.width,
                "height": img.height,
                "is_color": img.is_color,
                "is_full_page": img.is_full_page,
            }
            for img in images
        ],
    }
