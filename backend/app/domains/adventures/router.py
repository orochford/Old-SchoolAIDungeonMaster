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
    GraphVisualizationResponse,
    GraphVisualizationNode,
    GraphVisualizationEdge,
    GraphValidationReportResponse,
)

router = APIRouter()


async def parse_adventure_background(document_id: UUID):
    """Background task to parse an adventure module using multi-pass extraction."""
    import logging
    import os
    from app.config import settings
    from app.core.database import AsyncSessionLocal
    from app.domains.adventures.multipass_parser import MultiPassParser
    from app.domains.adventures.graph_rag import build_graph_from_module
    from app.domains.adventures.graph_rag.context_provider import GraphContextProvider

    logger = logging.getLogger(__name__)
    parser = None

    async with AsyncSessionLocal() as db:
        try:
            logger.info(f"Starting multi-pass adventure parsing for document {document_id}")
            parser = MultiPassParser(db)
            module = await parser.parse_adventure(document_id)

            # Invalidate any cached graph for this module (in case of re-parse)
            context_provider = GraphContextProvider(db)
            await context_provider.invalidate_cache(module.id)

            # Save the parsing log
            module.parsing_log = parser.parsing_log

            # Copy the source document's markdown path to the module for full-text reference
            result = await db.execute(
                select(PDFDocument).where(PDFDocument.id == document_id)
            )
            source_doc = result.scalar_one_or_none()
            if source_doc and source_doc.markdown_path and os.path.exists(source_doc.markdown_path):
                module.full_markdown_path = source_doc.markdown_path
                logger.info(f"Set full_markdown_path to {source_doc.markdown_path}")

            await db.commit()
            logger.info(f"Successfully parsed adventure document {document_id}")

            # Build knowledge graph for GraphRAG (uses already-extracted DB data, no LLM calls)
            try:
                logger.info(f"Building knowledge graph for module {module.id}")
                graph = await build_graph_from_module(db=db, module_id=module.id)
                # Save graph to disk using configured path
                graph_dir = settings.graph_storage_path
                os.makedirs(graph_dir, exist_ok=True)
                graph_path = os.path.join(graph_dir, f"{module.id}_graph.json")
                graph.save(graph_path)
                logger.info(f"Knowledge graph saved to {graph_path} with {len(graph.locations)} locations")
            except Exception as e:
                logger.error(f"Failed to build knowledge graph: {e}")
                # Don't fail the whole parse for graph errors - RAG still works as fallback

            # Export structured markdown from extracted data
            try:
                from app.domains.adventures.module_markdown_export import export_module_markdown
                structured_md = await export_module_markdown(db, module.id)

                # Derive storage path from the source document's markdown path
                md_path = module.full_markdown_path or ""
                if md_path:
                    structured_path = md_path.rsplit(".", 1)[0] + "_structured.md"
                else:
                    # Fallback: use markdown_storage_path with module id
                    md_dir = settings.markdown_storage_path
                    os.makedirs(md_dir, exist_ok=True)
                    structured_path = os.path.join(md_dir, f"{module.id}_structured.md")

                os.makedirs(os.path.dirname(structured_path), exist_ok=True)
                with open(structured_path, 'w', encoding='utf-8') as f:
                    f.write(structured_md)

                module.structured_markdown_path = structured_path
                logger.info(f"Structured markdown exported to {structured_path}")
            except Exception as e:
                logger.error(f"Failed to export structured markdown: {e}")
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


@router.get("/{module_id}/structured-markdown")
async def get_structured_markdown(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the structured markdown export for a module.

    Returns the enriched, organized markdown built from extracted DB data.
    Regenerates the file if missing from disk.
    """
    import os
    from app.domains.adventures.module_markdown_export import export_module_markdown
    from app.config import settings

    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Try to read from disk first
    if module.structured_markdown_path and os.path.exists(module.structured_markdown_path):
        with open(module.structured_markdown_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {
            "module_id": str(module_id),
            "title": module.title,
            "path": module.structured_markdown_path,
            "content": content,
        }

    # Regenerate if file is missing
    content = await export_module_markdown(db, module_id)

    # Save to disk
    md_path = module.full_markdown_path or ""
    if md_path:
        structured_path = md_path.rsplit(".", 1)[0] + "_structured.md"
    else:
        md_dir = settings.markdown_storage_path
        os.makedirs(md_dir, exist_ok=True)
        structured_path = os.path.join(md_dir, f"{module_id}_structured.md")

    os.makedirs(os.path.dirname(structured_path), exist_ok=True)
    with open(structured_path, 'w', encoding='utf-8') as f:
        f.write(content)

    module.structured_markdown_path = structured_path
    await db.commit()

    return {
        "module_id": str(module_id),
        "title": module.title,
        "path": structured_path,
        "content": content,
    }


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
    if location.exits and isinstance(location.exits, dict):
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


EXTRACT_MISSING_ROOMS_PROMPT = """You are extracting specific missing rooms from a tabletop RPG adventure module.

## ROOMS TO EXTRACT
The following room numbers/keys are referenced as exits from other rooms but were not found in the initial extraction.
Extract each one from the source text below.

{missing_rooms}

## EXISTING ROOMS (for reference)
{existing_rooms}

## OUTPUT FORMAT
Return a JSON object with a "locations" array. Each location should have:
```json
{{
  "locations": [
    {{
      "location_key": "2",
      "name": "Room Name",
      "dm_description": "Full DM description of the room including all details from the text",
      "read_aloud_text": "Player-facing boxed/read-aloud text if present",
      "features": [{{"feature": "stone altar", "details": "carved with runes"}}],
      "exits": {{"north": "1", "south": "3"}},
      "traps": [{{"trigger": "stepping on tile", "effect": "poison darts", "detection": "Search DC 15", "disarm": "Disable DC 12"}}],
      "secrets": [{{"type": "secret_door", "detection": "Search check", "description": "Hidden door behind tapestry"}}],
      "treasure": [{{"item": "gold coins", "value": "50 gp", "location": "in chest"}}],
      "dungeon_level": 1
    }}
  ]
}}
```

IMPORTANT:
- For exit values, use just the room NUMBER (e.g. "2" not "Room 2" or "Area 2")
- If a room key genuinely cannot be found in the text (e.g. it's a corridor or transition area, not a numbered/keyed room), still include it but set "not_found": true and provide a brief description based on context
- Extract ALL details: features, exits, traps, secrets, treasure
- Use dungeon_level 1 unless the text indicates otherwise

## SOURCE TEXT
{text}"""


async def _call_extraction_llm(prompt: str) -> dict:
    """Call the LLM for room extraction and parse JSON response."""
    import json
    import re
    from app.config import settings
    import logging

    logger = logging.getLogger(__name__)

    system_prompt = (
        "You are a precise data extractor for tabletop RPG adventure modules. "
        "CRITICAL: Always respond with valid JSON only. "
        "Your response must start with { and end with }. "
        "No markdown code blocks, no explanation text, just the JSON object."
    )

    if settings.processing_provider == "openai":
        import openai
        model = settings.processing_openai_model or "gpt-4o-mini"
        logger.info(f"[extract-missing] Using OpenAI ({model})")

        client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or ""
    else:
        import anthropic
        model = settings.processing_claude_model or "claude-haiku-4-5-20250101"
        logger.info(f"[extract-missing] Using Claude ({model})")

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await client.messages.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            system=system_prompt,
            max_tokens=8192,
        )
        content = ""
        if response.content:
            for block in response.content:
                if hasattr(block, 'text'):
                    content = block.text
                    break

    if not content:
        return {}

    # Parse JSON from response
    content = content.strip()
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    content = content.strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        # Try to find JSON object
        match = re.search(r'\{[\s\S]*\}', content)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    logger.error(f"[extract-missing] Failed to parse LLM response")
    return {}


@router.post("/{module_id}/extract-missing-rooms")
async def extract_missing_rooms(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Extract missing rooms and fix empty exits.

    Detects missing rooms in three ways:
    1. Dangling exits in the graph (rooms referenced but not extracted)
    2. Rooms found in the source text but not in the DB (by scanning for "N. ROOM NAME" patterns)
    3. Rooms with empty exits that need exit data re-extracted

    Uses targeted text extraction (finding the specific section for each room)
    instead of sending the full document, so rooms deep in the text aren't missed.
    """
    import os
    import re as _re
    import logging
    from app.config import settings
    from app.domains.adventures.graph_rag import build_graph_from_module
    from app.domains.adventures.graph_rag.context_provider import GraphContextProvider
    from app.domains.adventures.graph_rag.schema import ModuleGraph

    logger = logging.getLogger(__name__)

    # Get module
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Load source markdown text
    markdown_text = ""
    if module.full_markdown_path and os.path.exists(module.full_markdown_path):
        with open(module.full_markdown_path, 'r', encoding='utf-8') as f:
            markdown_text = f.read()

    if not markdown_text:
        result = await db.execute(
            select(PDFDocument).where(PDFDocument.id == module.pdf_document_id)
        )
        doc = result.scalar_one_or_none()
        if doc and doc.markdown_path and os.path.exists(doc.markdown_path):
            with open(doc.markdown_path, 'r', encoding='utf-8') as f:
                markdown_text = f.read()

    if not markdown_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No source text available for this module.",
        )

    # Get existing DB keys
    result = await db.execute(
        select(AdventureLocation)
        .where(AdventureLocation.module_id == module_id)
    )
    existing_locations = {loc.location_key: loc for loc in result.scalars().all()}
    existing_keys = set(existing_locations.keys())

    # --- Detection method 1: Scan source text for numbered room patterns ---
    # Find all "N. ROOM NAME" patterns to discover rooms we don't have
    text_room_keys: set[str] = set()
    for match in _re.finditer(r'(?:^|\n)\s*\*?\*?(\d+[a-z]?)\.\s+[A-Z][A-Z]', markdown_text):
        text_room_keys.add(match.group(1))

    missing_from_text = text_room_keys - existing_keys
    logger.info(f"[extract-missing] Source text has rooms: {sorted(text_room_keys, key=lambda x: int(x) if x.isdigit() else 0)}")
    logger.info(f"[extract-missing] Missing from DB: {sorted(missing_from_text, key=lambda x: int(x) if x.isdigit() else 0)}")

    # --- Detection method 2: Dangling graph exits ---
    graph_path = os.path.join(settings.graph_storage_path, f"{module_id}_graph.json")
    dangling_keys: set[str] = set()
    if os.path.exists(graph_path):
        graph = ModuleGraph.load(graph_path)
        location_ids = set(graph.locations.keys())
        for conn in graph.connections:
            if conn.to_id not in location_ids:
                dangling_keys.add(conn.to_id)

    # --- Detection method 3: Rooms with empty exits ---
    empty_exit_keys: set[str] = set()
    for key, loc in existing_locations.items():
        if not loc.exits or (isinstance(loc.exits, dict) and len(loc.exits) == 0):
            empty_exit_keys.add(key)

    # Combine all missing room keys
    all_missing = (missing_from_text | dangling_keys) - existing_keys
    # Filter out non-numeric keys that look bogus (like "east_corridor")
    all_missing = {k for k in all_missing if _re.match(r'^\d+[a-z]?$', k)}

    logger.info(f"[extract-missing] Total missing rooms to extract: {sorted(all_missing, key=lambda x: int(x) if x.isdigit() else 0)}")
    logger.info(f"[extract-missing] Rooms with empty exits to fix: {sorted(empty_exit_keys, key=lambda x: int(x) if x.isdigit() else 0)}")

    if not all_missing and not empty_exit_keys:
        return {
            "message": "No missing rooms and no empty exits to fix.",
            "extracted": 0,
            "exits_fixed": 0,
            "not_found": 0,
        }

    # --- Build targeted source text sections ---
    def _find_room_section(key: str) -> str:
        """Find the text section for a specific room key.

        Finds ALL matches and prefers the one that looks like an actual room
        description (ALL CAPS name like 'DINING ROOM') over wandering monster
        table entries ('Kobold (1-4)') which use the same 'N. Name' pattern.
        """
        escaped = _re.escape(key)
        pattern = rf'(?:^|\n)\s*\*?\*?{escaped}\.\s+([A-Z])'
        candidates = []
        for match in _re.finditer(pattern, markdown_text):
            start = max(0, match.start() - 50)
            end = min(len(markdown_text), match.start() + 3000)
            section = markdown_text[start:end]
            # Check if this looks like a room description (ALL CAPS name)
            # vs a monster table entry (mixed case like "Kobold", "Giant Rats")
            after_num = markdown_text[match.start():match.start() + 200]
            name_match = _re.search(rf'{escaped}\.\s+([A-Z][A-Z \'&]+)', after_num)
            is_room_desc = bool(name_match and len(name_match.group(1)) > 3)
            # Also check for "Monster:" or "Treasure" nearby (room description markers)
            has_room_markers = 'Monster:' in section or 'Treasure' in section
            candidates.append((section, is_room_desc, has_room_markers, match.start()))

        if not candidates:
            return ""

        # Prefer: ALL CAPS room name > has room markers > last match (later in doc)
        candidates.sort(key=lambda c: (c[1], c[2], c[3]), reverse=True)
        return candidates[0][0]

    # --- Phase 1: Extract missing rooms ---
    extracted_count = 0
    not_found_count = 0
    extracted_names = []

    if all_missing:
        source_sections = []
        for key in sorted(all_missing, key=lambda x: int(x) if x.isdigit() else 0):
            section = _find_room_section(key)
            if section:
                source_sections.append(f"--- Section for room {key} ---")
                source_sections.append(section)

        if source_sections:
            missing_rooms_text = ""
            for key in sorted(all_missing, key=lambda x: int(x) if x.isdigit() else 0):
                missing_rooms_text += f"- Room {key}: found in source text but not yet extracted\n"

            existing_rooms_text = ""
            for key in sorted(existing_keys, key=lambda x: int(x) if x.isdigit() else 0):
                loc = existing_locations[key]
                exits_str = ", ".join(f"{d}->{t}" for d, t in (loc.exits or {}).items()) if loc.exits else "none"
                existing_rooms_text += f"- {key}. {loc.name} (exits: {exits_str})\n"

            source_text = "\n\n".join(source_sections)
            logger.info(f"[extract-missing] Sending {len(source_sections)//2} sections ({len(source_text)} chars) for {len(all_missing)} missing rooms")

            prompt = EXTRACT_MISSING_ROOMS_PROMPT.format(
                missing_rooms=missing_rooms_text,
                existing_rooms=existing_rooms_text,
                text=source_text,
            )

            result_data = await _call_extraction_llm(prompt)

            for loc_data in (result_data or {}).get('locations', []):
                location_key = str(loc_data.get('location_key', ''))
                if not location_key:
                    continue
                if loc_data.get('not_found'):
                    not_found_count += 1
                    continue

                # Check if already exists
                exists = await db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module_id)
                    .where(AdventureLocation.location_key == location_key)
                )
                if exists.scalar_one_or_none():
                    continue

                location = AdventureLocation(
                    module_id=module_id,
                    location_key=location_key,
                    name=loc_data.get('name', f'Location {location_key}'),
                    dm_description=loc_data.get('dm_description', 'Extracted location.'),
                    read_aloud_text=loc_data.get('read_aloud_text'),
                    features=loc_data.get('features', []),
                    exits=loc_data.get('exits', {}) if isinstance(loc_data.get('exits'), dict) else {},
                    traps=loc_data.get('traps', []),
                    secrets=loc_data.get('secrets', []),
                    treasure=loc_data.get('treasure', []),
                    dungeon_level=loc_data.get('dungeon_level', 1),
                )
                db.add(location)
                extracted_count += 1
                extracted_names.append(f"{location_key}. {loc_data.get('name', '?')}")
                logger.info(f"[extract-missing] Extracted room {location_key}: {loc_data.get('name')}")

            await db.flush()

    # --- Phase 2: Fix empty exits on existing rooms ---
    exits_fixed = 0
    if empty_exit_keys:
        # Build sections for rooms with empty exits
        exit_sections = []
        exit_keys_to_fix = []
        for key in sorted(empty_exit_keys, key=lambda x: int(x) if x.isdigit() else 0):
            section = _find_room_section(key)
            if section:
                exit_sections.append(f"--- Section for room {key} ({existing_locations[key].name}) ---")
                exit_sections.append(section)
                exit_keys_to_fix.append(key)

        if exit_sections:
            exit_prompt = f"""You are extracting EXIT information for rooms in a tabletop RPG adventure module.

## ROOMS THAT NEED EXITS
The following rooms were extracted but their exit/connection data is missing.
For each room, find what other rooms it connects to.

{chr(10).join(f'- Room {k}. {existing_locations[k].name}' for k in exit_keys_to_fix)}

## ALL KNOWN ROOMS (for reference)
{chr(10).join(f'- {k}. {existing_locations[k].name}' for k in sorted(existing_keys, key=lambda x: int(x) if x.isdigit() else 0))}

## OUTPUT FORMAT
Return JSON with an "exits" object mapping room keys to their exit dicts:
```json
{{
  "exits": {{
    "2": {{"north": "1", "south": "3", "east": "5"}},
    "15": {{"west": "14", "north": "16"}}
  }}
}}
```

IMPORTANT:
- Exit values must be just the room NUMBER (e.g. "3" not "Room 3")
- Include ALL exits mentioned in the text (north, south, east, west, up, down, secret, etc.)
- If the text mentions corridors leading to other rooms, include those connections

## SOURCE TEXT
{chr(10).join(exit_sections)}"""

            exit_result = await _call_extraction_llm(exit_prompt)

            for room_key, room_exits in (exit_result or {}).get('exits', {}).items():
                room_key = str(room_key)
                if room_key not in existing_locations:
                    continue
                if not isinstance(room_exits, dict) or not room_exits:
                    continue
                loc = existing_locations[room_key]
                loc.exits = room_exits
                exits_fixed += 1
                logger.info(f"[extract-missing] Fixed exits for room {room_key}: {room_exits}")

            await db.flush()

    # --- Phase 3: Infer corridor connections between disconnected clusters ---
    # Many old-school modules connect rooms via corridors shown only on the map.
    # The text describes room contents but not corridor layout.
    # We detect disconnected clusters and ask the LLM to infer connections.
    corridors_added = 0

    # Reload all locations (including newly extracted ones)
    result = await db.execute(
        select(AdventureLocation)
        .where(AdventureLocation.module_id == module_id)
    )
    all_locations = {loc.location_key: loc for loc in result.scalars().all()}

    # Build adjacency from exits
    from collections import deque as _deque
    adj: dict[str, set[str]] = {}
    all_loc_keys = set(all_locations.keys())
    for key, loc in all_locations.items():
        if not loc.exits or not isinstance(loc.exits, dict):
            continue
        for direction, dest in loc.exits.items():
            dest_key = str(dest).strip()
            # Normalize destination (same logic as graph builder)
            num_match = _re.match(r'^(\d+[a-z]?)', dest_key)
            if num_match:
                dest_key = num_match.group(1)
            if dest_key in all_loc_keys:
                adj.setdefault(key, set()).add(dest_key)
                adj.setdefault(dest_key, set()).add(key)

    # BFS to find connected components
    visited: set[str] = set()
    components: list[set[str]] = []
    for start_key in all_loc_keys:
        if start_key in visited:
            continue
        comp: set[str] = set()
        queue = _deque([start_key])
        comp.add(start_key)
        while queue:
            node = queue.popleft()
            for nb in adj.get(node, set()):
                if nb not in comp:
                    comp.add(nb)
                    queue.append(nb)
        visited |= comp
        components.append(comp)

    if len(components) > 1:
        logger.info(f"[extract-missing] Graph has {len(components)} disconnected components")

        # Sort components by min room number for stable ordering
        def _comp_sort_key(comp):
            nums = [int(k) for k in comp if k.isdigit()]
            return min(nums) if nums else 999
        components.sort(key=_comp_sort_key)

        # Build room list with current exits for context
        rooms_context = ""
        for key in sorted(all_loc_keys, key=lambda x: int(x) if x.isdigit() else 999):
            loc = all_locations[key]
            exits_str = ", ".join(f"{d}->{t}" for d, t in (loc.exits or {}).items()) if loc.exits else "no exits"
            rooms_context += f"- {key}. {loc.name} (exits: {exits_str})\n"

        # Build component descriptions
        comp_desc = ""
        for i, comp in enumerate(components):
            sorted_keys = sorted(comp, key=lambda x: int(x) if x.isdigit() else 999)
            names = [f"{k}. {all_locations[k].name}" for k in sorted_keys[:10]]
            if len(sorted_keys) > 10:
                names.append(f"... and {len(sorted_keys)-10} more")
            comp_desc += f"\nCluster {i+1} ({len(comp)} rooms): {', '.join(names)}\n"

        # Get entrance/overview text for additional context
        entrance_section = ""
        entrance_match = _re.search(r'(?:ENTRANCE|ENCOUNTER AREAS).*?(?=\n\d+\.)', markdown_text, _re.DOTALL)
        if entrance_match:
            entrance_section = markdown_text[entrance_match.start():entrance_match.end()][:2000]

        corridor_prompt = f"""You are analyzing a tabletop RPG dungeon module to determine how rooms connect via corridors.

## PROBLEM
The dungeon map shows rooms connected by corridors, but the text only describes room contents.
The following clusters of rooms are DISCONNECTED from each other — they need corridor connections.

## DISCONNECTED CLUSTERS
{comp_desc}

## ALL ROOMS AND THEIR CURRENT EXITS
{rooms_context}

## ENTRANCE DESCRIPTION (shows how the dungeon layout starts)
{entrance_section}

## KEY TEXT SECTIONS
"""
        # Add boundary room sections (rooms at edges of each cluster)
        boundary_keys = set()
        for comp in components:
            sorted_keys = sorted(comp, key=lambda x: int(x) if x.isdigit() else 999)
            # Add first and last few rooms of each cluster as boundaries
            for k in sorted_keys[:3] + sorted_keys[-3:]:
                boundary_keys.add(k)

        for key in sorted(boundary_keys, key=lambda x: int(x) if x.isdigit() else 999):
            section = _find_room_section(key)
            if section:
                corridor_prompt += f"\n--- Room {key}. {all_locations[key].name} ---\n{section[:1000]}\n"

        corridor_prompt += f"""

## YOUR TASK
Determine which rooms should be connected to make the dungeon fully navigable.
Focus on connections between the disconnected clusters — how does a player get from one cluster to another?

Look for clues:
- The entrance description mentions corridors going in different directions
- Room numbering often follows map layout (adjacent numbers = nearby rooms)
- References like "across the hallway", "down the corridor", "nearby"
- The upper level (rooms 1-39) connects to the lower level (rooms 40+) somewhere

## OUTPUT FORMAT
Return JSON with connections to ADD. Each connection specifies which room gets a new exit:
```json
{{
  "connections": [
    {{"room": "1", "direction": "east", "destination": "3", "reason": "entrance corridor goes east"}},
    {{"room": "1", "direction": "west", "destination": "17", "reason": "entrance corridor goes west"}},
    {{"room": "39", "direction": "down", "destination": "40", "reason": "upper to lower level"}}
  ]
}}
```

IMPORTANT:
- Only add connections between DIFFERENT clusters (don't add within-cluster connections)
- Use reasonable directions (north, south, east, west, up, down, stairs_down, etc.)
- Destination values must be just the room NUMBER
- Include a brief reason for each connection
- Add connections in BOTH directions (if room 1 goes east to 3, also add room 3 goes west to 1)
"""

        corridor_result = await _call_extraction_llm(corridor_prompt)

        for conn_data in (corridor_result or {}).get('connections', []):
            room_key = str(conn_data.get('room', ''))
            direction = conn_data.get('direction', '')
            destination = str(conn_data.get('destination', ''))

            if not room_key or not direction or not destination:
                continue
            if room_key not in all_locations:
                continue
            # Only accept numeric destination keys
            if not _re.match(r'^\d+[a-z]?$', destination):
                continue

            loc = all_locations[room_key]
            current_exits = dict(loc.exits) if loc.exits and isinstance(loc.exits, dict) else {}

            # Don't overwrite existing exits for this direction
            if direction in current_exits:
                continue

            current_exits[direction] = destination
            loc.exits = current_exits
            corridors_added += 1
            logger.info(
                f"[extract-missing] Corridor connection: {room_key} ({loc.name}) "
                f"-> {direction} -> {destination} ({all_locations.get(destination, '?')})"
            )

        if corridors_added:
            await db.flush()
            logger.info(f"[extract-missing] Added {corridors_added} corridor connections")

    # --- Phase 4: Map-based corridor discovery using vision AI ---
    map_corridors_added = 0
    try:
        from app.domains.adventures.map_corridor_discovery import (
            discover_corridors_from_maps,
            merge_map_connections_into_exits,
        )

        # Reload all locations (Phase 1-3 may have modified them)
        result = await db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
        )
        all_locations_phase4 = {loc.location_key: loc for loc in result.scalars().all()}

        if module.pdf_document_id and all_locations_phase4:
            rooms_dict = {
                key: {"name": loc.name, "dungeon_level": loc.dungeon_level or 1}
                for key, loc in all_locations_phase4.items()
            }

            corridor_result = await discover_corridors_from_maps(
                db, module.pdf_document_id, rooms_dict
            )

            if corridor_result.connections:
                logger.info(
                    f"[extract-missing] Map vision discovered "
                    f"{len(corridor_result.connections)} corridor connections"
                )

                # Build existing exits dict
                existing_exits_p4 = {}
                for key, loc in all_locations_phase4.items():
                    if loc.exits and isinstance(loc.exits, dict):
                        existing_exits_p4[key] = dict(loc.exits)
                    else:
                        existing_exits_p4[key] = {}

                merged_exits_p4 = merge_map_connections_into_exits(
                    corridor_result.connections, existing_exits_p4
                )

                # Update DB with merged exits
                for key, new_exits in merged_exits_p4.items():
                    old_exits = existing_exits_p4.get(key, {})
                    if new_exits != old_exits:
                        loc = all_locations_phase4.get(key)
                        if loc:
                            loc.exits = new_exits
                            map_corridors_added += len(new_exits) - len(old_exits)

                if map_corridors_added:
                    await db.flush()
                    logger.info(
                        f"[extract-missing] Added {map_corridors_added} "
                        f"map-based corridor connections"
                    )

            if corridor_result.errors:
                for err in corridor_result.errors:
                    logger.warning(f"[extract-missing] Map vision: {err}")

    except Exception as e:
        logger.error(f"[extract-missing] Phase 4 (map corridors) failed: {e}")
        # Don't fail the whole endpoint for map vision errors

    # --- Phase 5: Connection reconciliation pass ---
    reconciliation_changes = 0
    reconciliation_confidence = ""
    clusters_before = 0
    clusters_after = 0
    try:
        from app.domains.adventures.connection_reconciliation import reconcile_connections

        recon_result = await reconcile_connections(db, module_id, auto_apply=True)
        reconciliation_changes = len(recon_result.changes)
        reconciliation_confidence = recon_result.confidence
        clusters_before = recon_result.disconnected_clusters

        # Recount clusters after
        from app.domains.adventures.connection_reconciliation import _find_clusters
        recon_locs = await db.execute(
            select(AdventureLocation).where(AdventureLocation.module_id == module_id)
        )
        recon_all = {loc.location_key: loc for loc in recon_locs.scalars().all()}
        recon_exits = {
            k: dict(loc.exits) if loc.exits and isinstance(loc.exits, dict) else {}
            for k, loc in recon_all.items()
        }
        new_clusters = _find_clusters(set(recon_all.keys()), recon_exits)
        clusters_after = len(new_clusters)

        if reconciliation_changes:
            await db.flush()
            logger.info(
                f"[extract-missing] Phase 5: {reconciliation_changes} reconciliation changes "
                f"(confidence: {reconciliation_confidence}, clusters: {clusters_before} -> {clusters_after})"
            )

    except Exception as e:
        logger.error(f"[extract-missing] Phase 5 (reconciliation) failed: {e}")

    # Update module location count
    from sqlalchemy import func as sqla_func
    count_result = await db.execute(
        select(sqla_func.count(AdventureLocation.id))
        .where(AdventureLocation.module_id == module_id)
    )
    module.location_count = count_result.scalar() or 0
    await db.commit()

    # Rebuild graph
    context_provider = GraphContextProvider(db)
    await context_provider.invalidate_cache(module_id)
    if os.path.exists(graph_path):
        os.remove(graph_path)
    graph = await build_graph_from_module(db=db, module_id=module_id)
    os.makedirs(os.path.dirname(graph_path), exist_ok=True)
    graph.save(graph_path)

    # Regenerate structured markdown (exits/rooms changed)
    try:
        from app.domains.adventures.module_markdown_export import export_module_markdown
        structured_md = await export_module_markdown(db, module_id)

        md_path = module.full_markdown_path or ""
        if md_path:
            structured_path = md_path.rsplit(".", 1)[0] + "_structured.md"
        else:
            from app.config import settings as _settings
            md_dir = _settings.markdown_storage_path
            os.makedirs(md_dir, exist_ok=True)
            structured_path = os.path.join(md_dir, f"{module_id}_structured.md")

        os.makedirs(os.path.dirname(structured_path), exist_ok=True)
        with open(structured_path, 'w', encoding='utf-8') as f:
            f.write(structured_md)

        module.structured_markdown_path = structured_path
        await db.commit()
        logger.info(f"[extract-missing] Regenerated structured markdown at {structured_path}")
    except Exception as e:
        logger.error(f"[extract-missing] Failed to regenerate structured markdown: {e}")

    # Check remaining issues
    remaining_dangling = 0
    new_location_ids = set(graph.locations.keys())
    for conn in graph.connections:
        if conn.to_id not in new_location_ids:
            remaining_dangling += 1

    msg_parts = []
    if extracted_count:
        msg_parts.append(f"Extracted {extracted_count} rooms")
    if exits_fixed:
        msg_parts.append(f"fixed exits on {exits_fixed} rooms")
    if corridors_added:
        msg_parts.append(f"added {corridors_added} text-inferred corridor connections")
    if map_corridors_added:
        msg_parts.append(f"added {map_corridors_added} map-based corridor connections")
    if reconciliation_changes:
        msg_parts.append(f"reconciled {reconciliation_changes} connection changes")
    if not_found_count:
        msg_parts.append(f"{not_found_count} not found in text")
    msg = ". ".join(msg_parts) + f". Graph rebuilt ({len(graph.locations)} locations)."

    # Check connectivity after rebuild
    from collections import deque as _deque2
    node_ids = set(graph.locations.keys())
    g_adj: dict[str, set[str]] = {}
    for conn in graph.connections:
        g_adj.setdefault(conn.from_id, set()).add(conn.to_id)
        g_adj.setdefault(conn.to_id, set()).add(conn.from_id)
    reachable: set[str] = set()
    if '1' in node_ids:
        q = _deque2(['1'])
        reachable.add('1')
        while q:
            n = q.popleft()
            for nb in g_adj.get(n, set()):
                if nb not in reachable:
                    reachable.add(nb)
                    q.append(nb)

    return {
        "message": msg,
        "extracted": extracted_count,
        "extracted_names": extracted_names,
        "exits_fixed": exits_fixed,
        "corridors_added": corridors_added,
        "map_corridors_added": map_corridors_added,
        "reconciliation_changes": reconciliation_changes,
        "reconciliation_confidence": reconciliation_confidence,
        "disconnected_clusters_before": clusters_before,
        "disconnected_clusters_after": clusters_after,
        "not_found": not_found_count,
        "remaining_dangling": remaining_dangling,
        "total_locations": len(graph.locations),
        "reachable_from_start": len(reachable),
    }

@router.post("/{module_id}/reconcile-connections")
async def reconcile_connections_endpoint(
    module_id: UUID,
    auto_apply: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Run a connection reconciliation pass on the dungeon graph.

    Sends map images + complete current exit state to vision AI to produce
    an authoritative exit map. Unlike the additive-only merge in Phase 4,
    this pass can ADD, REMOVE, and CORRECT connections.

    Query params:
        auto_apply: If True (default), writes corrected exits to DB and
                    rebuilds the graph + structured markdown.
    """
    import os
    from collections import deque as _deque3
    from app.config import settings
    from app.domains.adventures.graph_rag import build_graph_from_module
    from app.domains.adventures.graph_rag.context_provider import GraphContextProvider
    from app.domains.adventures.connection_reconciliation import (
        reconcile_connections,
        _find_clusters,
    )

    # Verify module exists
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Run reconciliation
    recon_result = await reconcile_connections(db, module_id, auto_apply=auto_apply)

    if recon_result.errors and not recon_result.changes:
        return {
            "message": f"Reconciliation failed: {'; '.join(recon_result.errors)}",
            "changes": [],
            "confidence": recon_result.confidence,
            "disconnected_clusters_before": recon_result.disconnected_clusters,
            "disconnected_clusters_after": recon_result.disconnected_clusters,
            "total_locations": recon_result.rooms_processed,
            "reachable_from_start": 0,
            "auto_applied": auto_apply,
        }

    # Count clusters after
    loc_result = await db.execute(
        select(AdventureLocation).where(AdventureLocation.module_id == module_id)
    )
    all_locs = {loc.location_key: loc for loc in loc_result.scalars().all()}
    current_exits = {
        k: dict(loc.exits) if loc.exits and isinstance(loc.exits, dict) else {}
        for k, loc in all_locs.items()
    }
    clusters_after = len(_find_clusters(set(all_locs.keys()), current_exits))

    # Rebuild graph + structured markdown if changes were applied
    reachable_count = 0
    if auto_apply and recon_result.changes:
        await db.commit()

        graph_dir = settings.graph_storage_path
        graph_path = os.path.join(graph_dir, f"{module_id}_graph.json")

        context_provider = GraphContextProvider(db)
        await context_provider.invalidate_cache(module_id)
        if os.path.exists(graph_path):
            os.remove(graph_path)
        graph = await build_graph_from_module(db=db, module_id=module_id)
        os.makedirs(os.path.dirname(graph_path), exist_ok=True)
        graph.save(graph_path)

        # Regenerate structured markdown
        try:
            from app.domains.adventures.module_markdown_export import export_module_markdown
            structured_md = await export_module_markdown(db, module_id)
            md_path = module.full_markdown_path or ""
            if md_path:
                structured_path = md_path.rsplit(".", 1)[0] + "_structured.md"
            else:
                md_dir = settings.markdown_storage_path
                os.makedirs(md_dir, exist_ok=True)
                structured_path = os.path.join(md_dir, f"{module_id}_structured.md")
            os.makedirs(os.path.dirname(structured_path), exist_ok=True)
            with open(structured_path, 'w', encoding='utf-8') as f:
                f.write(structured_md)
            module.structured_markdown_path = structured_path
            await db.commit()
        except Exception:
            pass

        # BFS reachability check
        node_ids = set(graph.locations.keys())
        g_adj: dict[str, set[str]] = {}
        for conn in graph.connections:
            g_adj.setdefault(conn.from_id, set()).add(conn.to_id)
            g_adj.setdefault(conn.to_id, set()).add(conn.from_id)
        reachable: set[str] = set()
        if '1' in node_ids:
            q = _deque3(['1'])
            reachable.add('1')
            while q:
                n = q.popleft()
                for nb in g_adj.get(n, set()):
                    if nb not in reachable:
                        reachable.add(nb)
                        q.append(nb)
        reachable_count = len(reachable)

    # Format changes for response
    changes_list = [
        {
            "room": c.room_key,
            "type": c.change_type,
            "direction": c.direction,
            "destination": c.destination,
            "old_direction": c.old_direction,
            "old_destination": c.old_destination,
            "reason": c.reason,
        }
        for c in recon_result.changes
    ]

    return {
        "message": f"Reconciled {recon_result.rooms_processed} rooms. {len(recon_result.changes)} changes made.",
        "changes": changes_list,
        "confidence": recon_result.confidence,
        "disconnected_clusters_before": recon_result.disconnected_clusters,
        "disconnected_clusters_after": clusters_after,
        "total_locations": recon_result.rooms_processed,
        "reachable_from_start": reachable_count,
        "auto_applied": auto_apply,
    }


@router.post("/{module_id}/rebuild-graph")
async def rebuild_graph(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Rebuild the knowledge graph for an adventure module.

    Deletes the cached graph and rebuilds from current database data.
    Useful when source_text or other location data has been updated.
    """
    import os
    from app.config import settings
    from app.domains.adventures.graph_rag import build_graph_from_module
    from app.domains.adventures.graph_rag.context_provider import GraphContextProvider

    # Verify module exists
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Invalidate cache
    context_provider = GraphContextProvider(db)
    await context_provider.invalidate_cache(module_id)

    # Delete existing graph file
    graph_dir = settings.graph_storage_path
    graph_path = os.path.join(graph_dir, f"{module_id}_graph.json")
    if os.path.exists(graph_path):
        os.remove(graph_path)

    # Rebuild
    graph = await build_graph_from_module(db=db, module_id=module_id)
    os.makedirs(graph_dir, exist_ok=True)
    graph.save(graph_path)

    return {
        "message": "Graph rebuilt successfully",
        "module_id": str(module_id),
        "locations": len(graph.locations),
        "creatures": len(graph.creatures),
        "npcs": len(graph.npcs),
        "items": len(graph.items),
    }


def _parse_hd_value(hd_str: str) -> float:
    """Parse HD string like '2+1', '1/2', '3' to numeric value."""
    hd_str = str(hd_str).strip()
    if '/' in hd_str:
        parts = hd_str.split('/')
        try:
            return float(parts[0]) / float(parts[1])
        except (ValueError, ZeroDivisionError):
            return 1.0
    if '+' in hd_str:
        parts = hd_str.split('+')
        try:
            return float(parts[0]) + float(parts[1]) * 0.125
        except ValueError:
            return 1.0
    try:
        return float(hd_str)
    except ValueError:
        return 1.0


@router.get("/{module_id}/graph", response_model=GraphVisualizationResponse)
async def get_module_graph(
    module_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get the knowledge graph for visualization as nodes and edges."""
    from app.domains.adventures.graph_rag.context_provider import GraphContextProvider

    # Verify module exists
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Load the graph
    provider = GraphContextProvider(db)
    graph = await provider.get_graph(module_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge graph not found. Try rebuilding it.",
        )

    # Build location-level lookup sets for boolean indicators
    locations_with_creatures: set[str] = set()
    locations_with_items: set[str] = set()
    locations_with_npcs: set[str] = set()
    locations_with_traps: set[str] = set()
    locations_with_secrets: set[str] = set()

    for edge in graph.locations_of:
        loc_id = edge.location_id
        entity_id = edge.entity_id
        if entity_id in graph.creatures:
            locations_with_creatures.add(loc_id)
        if entity_id in graph.npcs:
            locations_with_npcs.add(loc_id)

    for edge in graph.containment:
        # Items contained directly in locations
        container_id = edge.container_id
        if container_id in graph.locations:
            locations_with_items.add(container_id)

    for edge in graph.trigger_links:
        loc_id = edge.location_id
        trigger = graph.triggers.get(edge.trigger_id)
        if trigger and trigger.trigger_type.value == "trap":
            locations_with_traps.add(loc_id)

    for edge in graph.feature_links:
        loc_id = edge.location_id
        feature = graph.features.get(edge.feature_id)
        if feature and feature.is_secret:
            locations_with_secrets.add(loc_id)

    # Also check connections for secret passages
    for conn in graph.connections:
        if conn.is_secret:
            locations_with_secrets.add(conn.from_id)
            locations_with_secrets.add(conn.to_id)

    # Build creature summaries per location
    location_creature_info: dict[str, tuple[list[str], float]] = {}
    for edge in graph.locations_of:
        creature = graph.creatures.get(edge.entity_id)
        if creature:
            loc_id = edge.location_id
            if loc_id not in location_creature_info:
                location_creature_info[loc_id] = ([], 0.0)
            parts, total_hd = location_creature_info[loc_id]
            parts.append(f"{creature.count} {creature.name}" if creature.count > 1 else creature.name)
            hd_val = _parse_hd_value(creature.hd) * creature.count
            location_creature_info[loc_id] = (parts, total_hd + hd_val)

    # Find locations referenced in connections but missing from graph
    # These are rooms the parser extracted exits to but didn't create location nodes for
    graph_loc_ids = set(graph.locations.keys())
    referenced_ids: set[str] = set()
    for conn in graph.connections:
        referenced_ids.add(conn.from_id)
        referenced_ids.add(conn.to_id)
    missing_ids = referenced_ids - graph_loc_ids

    # Try to fill in missing locations from the DB
    db_locations_by_key: dict[str, AdventureLocation] = {}
    if missing_ids:
        result = await db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module_id)
        )
        for loc in result.scalars().all():
            db_locations_by_key[loc.location_key] = loc

    # Build visualization nodes
    nodes = []
    all_node_ids: set[str] = set()
    for loc_id, loc in graph.locations.items():
        creature_info = location_creature_info.get(loc_id)
        creature_summary = ""
        encounter_hd_total = 0.0
        if creature_info:
            parts, total_hd = creature_info
            summary = ", ".join(parts)
            creature_summary = summary[:40] + "…" if len(summary) > 40 else summary
            encounter_hd_total = round(total_hd, 1)

        is_entrance = loc.key == "1" or "entrance" in loc.name.lower()

        nodes.append(GraphVisualizationNode(
            id=loc_id,
            key=loc.key,
            name=loc.name,
            dungeon_level=loc.dungeon_level,
            is_empty=loc.is_empty,
            has_creatures=loc_id in locations_with_creatures,
            has_items=loc_id in locations_with_items,
            has_traps=loc_id in locations_with_traps,
            has_secrets=loc_id in locations_with_secrets,
            has_npcs=loc_id in locations_with_npcs,
            is_entrance=is_entrance,
            creature_summary=creature_summary,
            encounter_hd_total=encounter_hd_total,
        ))
        all_node_ids.add(loc_id)

    # Add stub nodes for missing locations that exist in the DB
    for mid in missing_ids:
        if mid in db_locations_by_key:
            db_loc = db_locations_by_key[mid]
            nodes.append(GraphVisualizationNode(
                id=mid,
                key=db_loc.location_key,
                name=db_loc.name,
                dungeon_level=db_loc.dungeon_level,
                is_empty=not bool(db_loc.traps or db_loc.secrets or db_loc.treasure),
                has_creatures=False,
                has_items=bool(db_loc.treasure),
                has_traps=bool(db_loc.traps),
                has_secrets=bool(db_loc.secrets),
                has_npcs=False,
            ))
            all_node_ids.add(mid)

    # Build visualization edges with bidirectional deduplication
    # Only include edges where both endpoints exist as nodes
    seen_pairs: set[tuple[str, str]] = set()
    edges = []
    for conn in graph.connections:
        if conn.from_id not in all_node_ids or conn.to_id not in all_node_ids:
            continue
        pair = tuple(sorted([conn.from_id, conn.to_id]))
        if pair in seen_pairs and not conn.is_one_way:
            continue
        seen_pairs.add(pair)
        edges.append(GraphVisualizationEdge(
            from_id=conn.from_id,
            to_id=conn.to_id,
            direction=conn.direction,
            is_secret=conn.is_secret,
            is_one_way=conn.is_one_way,
        ))

    # Build validation report if available
    validation = None
    if graph.validation_report:
        validation = GraphValidationReportResponse(
            dangling_exits=graph.validation_report.dangling_exits,
            orphan_locations=graph.validation_report.orphan_locations,
            total_locations=graph.validation_report.total_locations,
            total_connections=graph.validation_report.total_connections,
        )

    return GraphVisualizationResponse(
        module_id=str(module_id),
        module_title=module.title,
        nodes=nodes,
        edges=edges,
        validation_report=validation,
    )


@router.get("/{module_id}/graph/player")
async def get_player_graph(
    module_id: UUID,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a player-facing graph filtered by discovered locations.

    Only includes locations the player has visited (from session.adventure_state.visited_locations).
    Strips secrets, traps, and hidden features. Highlights current location.
    Adjacent undiscovered locations appear as mystery '?' nodes.

    Note: module_id can also be resolved from the session's campaign if needed -
    use the /sessions/{session_id}/player-graph endpoint for that.
    """
    from app.domains.adventures.graph_rag.context_provider import GraphContextProvider
    from app.domains.sessions.models import Session

    # Verify module exists
    result = await db.execute(
        select(AdventureModule).where(AdventureModule.id == module_id)
    )
    module = result.scalar_one_or_none()
    if not module:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Adventure module not found",
        )

    # Get session for visited locations
    result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found",
        )

    adventure_state = dict(session.adventure_state or {})
    visited_keys = set(adventure_state.get("visited_locations", []))
    current_location_key = adventure_state.get("current_location_key")

    # Load the full graph
    provider = GraphContextProvider(db)
    graph = await provider.get_graph(module_id)
    if not graph:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge graph not found. Try rebuilding it.",
        )

    # Find adjacent undiscovered locations (mystery "?" nodes)
    adjacent_undiscovered: set[str] = set()
    for conn in graph.connections:
        if conn.from_id in visited_keys and conn.to_id not in visited_keys:
            adjacent_undiscovered.add(conn.to_id)
        if conn.to_id in visited_keys and conn.from_id not in visited_keys:
            adjacent_undiscovered.add(conn.from_id)

    # Build nodes for visited locations (stripped of secrets)
    nodes = []
    all_node_ids: set[str] = set()

    for loc_id, loc in graph.locations.items():
        if loc_id not in visited_keys:
            continue
        nodes.append(GraphVisualizationNode(
            id=loc_id,
            key=loc.key,
            name=loc.name,
            dungeon_level=loc.dungeon_level,
            is_empty=loc.is_empty,
            has_creatures=False,  # Don't reveal creatures on player map
            has_items=False,      # Don't reveal items on player map
            has_traps=False,      # Don't reveal traps on player map
            has_secrets=False,    # Don't reveal secrets on player map
            has_npcs=False,       # Don't reveal NPCs on player map
        ))
        all_node_ids.add(loc_id)

    # Add mystery nodes for adjacent undiscovered
    for adj_id in adjacent_undiscovered:
        adj_loc = graph.locations.get(adj_id)
        nodes.append(GraphVisualizationNode(
            id=adj_id,
            key=adj_id,
            name="?",
            dungeon_level=adj_loc.dungeon_level if adj_loc else 1,
            is_empty=False,
            has_creatures=False,
            has_items=False,
            has_traps=False,
            has_secrets=False,
            has_npcs=False,
        ))
        all_node_ids.add(adj_id)

    # Build edges: only where at least one endpoint is visited and other is in our node set
    seen_pairs: set[tuple[str, str]] = set()
    edges = []
    for conn in graph.connections:
        if conn.from_id not in all_node_ids or conn.to_id not in all_node_ids:
            continue
        if conn.is_secret:
            continue  # Don't show secret passages on player map
        pair = tuple(sorted([conn.from_id, conn.to_id]))
        if pair in seen_pairs and not conn.is_one_way:
            continue
        seen_pairs.add(pair)
        edges.append(GraphVisualizationEdge(
            from_id=conn.from_id,
            to_id=conn.to_id,
            direction=conn.direction,
            is_secret=False,
            is_one_way=conn.is_one_way,
        ))

    return {
        "module_id": str(module_id),
        "module_title": module.title,
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
        "current_location_key": current_location_key,
        "visited_count": len(visited_keys),
        "total_locations": len(graph.locations),
    }


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
