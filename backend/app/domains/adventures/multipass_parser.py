"""Multi-pass LLM-powered adventure module parsing service.

This parser uses a context-building multi-pass system where each pass
builds on previous passes, maintaining a running context document that
the LLM references for improved extraction accuracy.

Passes:
    0. Preprocessing (regex-based)
    1. Structure & Overview
    2. Location Details (batched)
    3. Inhabitants & Threats
    4. DM Guidance
    5. Player Experience
    6. Narrative & Connections
    7. Verification & Gap Filling
"""

import logging
import os
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.domains.sourcebooks.models import PDFDocument, PDFChunk
from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, AdventureItem, AdventureStoryBeat,
    ParsingStatus,
)
from app.domains.adventures.extraction_context import ExtractionContext
from app.domains.adventures.preprocessor import AdventurePreprocessor
from app.domains.adventures.passes import (
    OverviewPass,
    LocationsPass,
    MapValidationPass,
    InhabitantsPass,
    DMGuidancePass,
    PlayerContentPass,
    NarrativePass,
    VerificationPass,
)
from app.rag.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


class MultiPassParser:
    """Orchestrates multi-pass extraction with context building.

    This parser processes adventure modules in 7 passes, with each pass
    building on the context accumulated from previous passes.

    The key insight is that each extraction stage benefits from knowing
    what was extracted in earlier stages. For example:
    - Pass 3 (encounters) knows all locations from Pass 2
    - Pass 4 (DM guidance) knows all encounters and NPCs
    - Pass 7 (verification) can identify gaps from all previous passes
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.preprocessor = AdventurePreprocessor()
        self.embedding_service = EmbeddingService()
        self.context = ExtractionContext()
        self.parsing_log: List[str] = []

        # Initialize passes
        self.passes = [
            OverviewPass(db),       # Pass 1
            LocationsPass(db),      # Pass 2
            MapValidationPass(db),  # Pass 2.5
            InhabitantsPass(db),    # Pass 3
            DMGuidancePass(db),     # Pass 4
            PlayerContentPass(db),  # Pass 5
            NarrativePass(db),      # Pass 6
            VerificationPass(db),   # Pass 7
        ]

    def _log(self, message: str) -> None:
        """Add a message to the parsing log."""
        logger.info(message)
        self.parsing_log.append(message)

    async def parse_adventure(
        self,
        document_id: UUID,
        progress_callback: Optional[callable] = None,
        embeddings_only: bool = False,
    ) -> AdventureModule:
        """Parse an adventure module PDF into structured data using multi-pass extraction.

        Args:
            document_id: UUID of the PDFDocument to parse
            progress_callback: Optional callback for progress updates (0-100)
            embeddings_only: If True, skip LLM extraction and only generate embeddings

        Returns:
            The created AdventureModule with all parsed data
        """
        # Get the document
        result = await self.db.execute(
            select(PDFDocument).where(PDFDocument.id == document_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            raise ValueError(f"Document {document_id} not found")

        # Check if already parsed
        existing = await self.db.execute(
            select(AdventureModule).where(AdventureModule.pdf_document_id == document_id)
        )
        module = existing.scalar_one_or_none()

        if embeddings_only:
            if not module:
                raise ValueError("No existing module found - run full parse first")
            module.parsing_status = ParsingStatus.PROCESSING
            module.parsing_error = None
            module.parsing_progress = 90
            await self.db.flush()
            return await self._run_embeddings_only(module, progress_callback)

        if module:
            # Reset for re-parsing
            module.parsing_status = ParsingStatus.PROCESSING
            module.parsing_error = None
            module.parsing_progress = 0
            await self._clear_module_data(module.id)
        else:
            # Create new module
            module = AdventureModule(
                pdf_document_id=document_id,
                title=document.title or document.original_filename,
                parsing_status=ParsingStatus.PROCESSING,
            )
            self.db.add(module)
            await self.db.flush()

        try:
            # Reset parsing state
            self.parsing_log = []
            self.context = ExtractionContext()
            self._log(f"Starting multi-pass parsing for document {document_id}")

            # Get document text
            full_text = await self._get_document_text(document_id)

            if not full_text:
                raise ValueError("No text content found in document")

            self._log(f"Extracted {len(full_text)} characters from {document.original_filename}")

            # Pass 0: Preprocessing
            self._log("Pass 0/7: Preprocessing document structure...")
            await self._update_progress(module, 2, progress_callback)
            preprocessed = self.preprocessor.preprocess(full_text)
            self._log(f"  → Found {len(preprocessed['rooms'])} rooms")
            self._log(f"  → Found {len(preprocessed['wandering_tables'])} wandering tables")
            self._log(f"  → Found {len(preprocessed.get('outline', []))} outline entries")
            self._log(f"  → Found {len(preprocessed.get('dm_sections', []))} DM sections")
            await self._update_progress(module, 5, progress_callback)

            # Run each pass, building context
            total_passes = len(self.passes)
            for i, pass_handler in enumerate(self.passes):
                pass_num = i + 1
                self._log(f"Pass {pass_num}/{total_passes}: {pass_handler.description}...")

                # Calculate progress range for this pass
                pass_start_progress = 5 + int(85 * i / total_passes)
                pass_end_progress = 5 + int(85 * (i + 1) / total_passes)
                await self._update_progress(module, pass_start_progress, progress_callback)

                # Execute the pass
                try:
                    updates = await pass_handler.execute(
                        module=module,
                        full_text=full_text,
                        preprocessed=preprocessed,
                        context=self.context,
                    )

                    # Merge updates into context
                    self.context.merge(updates)

                    # Log pass results
                    for msg in pass_handler.get_log_messages():
                        self._log(f"  → {msg}")
                    pass_handler.clear_log_messages()

                except Exception as e:
                    self._log(f"  → ERROR: {str(e)}")
                    logger.exception(f"Pass {pass_num} failed: {e}")
                    # Continue with other passes

                await self._update_progress(module, pass_end_progress, progress_callback)
                await self._persist_pass_results(module)

            # Post-parse completeness verification
            preprocessed_keys = {str(r.get('location_key', '')) for r in preprocessed.get('rooms', [])}
            result = await self.db.execute(
                select(AdventureLocation.location_key)
                .where(AdventureLocation.module_id == module.id)
            )
            extracted_keys = {row[0] for row in result.fetchall()}
            still_missing = preprocessed_keys - extracted_keys

            if still_missing:
                self._log(f"WARNING: {len(still_missing)} rooms still missing after all passes: {sorted(still_missing)}")
                self.context.verification_issues.append(
                    f"MISSING ROOMS: {len(still_missing)} rooms from preprocessor not extracted: {sorted(still_missing)}"
                )
            else:
                self._log(f"Completeness check: all {len(preprocessed_keys)} preprocessed rooms extracted successfully")

            # Generate embeddings
            self._log("Generating search embeddings...")
            await self._update_progress(module, 92, progress_callback)
            await self._generate_embeddings(module)
            await self._update_progress(module, 98, progress_callback)

            # Update final stats
            await self._update_module_stats(module)

            # Log verification issues
            if self.context.verification_issues:
                self._log("Verification warnings:")
                for issue in self.context.verification_issues:
                    self._log(f"  ⚠ {issue}")

            if self.context.gaps_filled:
                self._log(f"Gap-filled: {len(self.context.gaps_filled)} items")

            module.parsing_status = ParsingStatus.COMPLETED
            module.parsing_progress = 100

            self._log("Multi-pass parsing complete!")
            self._log(f"  → {module.location_count} locations")
            self._log(f"  → {module.npc_count} NPCs")
            self._log(f"  → {module.encounter_count} encounters")
            self._log(f"  → {module.item_count} items")

            await self.db.flush()
            await self._update_progress(module, 100, progress_callback)

            return module

        except Exception as e:
            logger.exception(f"Failed to parse adventure {document_id}")
            module.parsing_status = ParsingStatus.FAILED
            module.parsing_error = str(e)
            await self.db.flush()
            raise

    async def _get_document_text(self, document_id: UUID) -> str:
        """Get all text from document, preferring markdown file if available."""
        result = await self.db.execute(
            select(PDFDocument).where(PDFDocument.id == document_id)
        )
        document = result.scalar_one_or_none()

        if document and document.markdown_path and os.path.exists(document.markdown_path):
            try:
                with open(document.markdown_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    logger.info(f"Using markdown file: {document.markdown_path} ({len(content)} chars)")
                    return content
            except Exception as e:
                logger.warning(f"Failed to read markdown file: {e}")

        # Fall back to chunks
        result = await self.db.execute(
            select(PDFChunk)
            .where(PDFChunk.document_id == document_id)
            .order_by(PDFChunk.chunk_index)
        )
        chunks = list(result.scalars().all())
        logger.info(f"Using {len(chunks)} chunks (no markdown file)")
        return "\n\n".join(chunk.content for chunk in chunks)

    async def _clear_module_data(self, module_id: UUID) -> None:
        """Clear existing parsed data for a module."""
        from sqlalchemy import delete

        await self.db.execute(delete(AdventureStoryBeat).where(AdventureStoryBeat.module_id == module_id))
        await self.db.execute(delete(AdventureItem).where(AdventureItem.module_id == module_id))
        await self.db.execute(delete(AdventureEncounter).where(AdventureEncounter.module_id == module_id))
        await self.db.execute(delete(AdventureNPC).where(AdventureNPC.module_id == module_id))
        await self.db.execute(delete(AdventureLocation).where(AdventureLocation.module_id == module_id))
        await self.db.flush()

    async def _update_progress(
        self,
        module: AdventureModule,
        progress: int,
        callback: Optional[callable] = None,
    ) -> None:
        """Update parsing progress and save log."""
        module.parsing_progress = progress
        module.parsing_log = list(self.parsing_log)
        await self.db.commit()
        if callback:
            callback(progress)

    async def _persist_pass_results(self, module: AdventureModule) -> None:
        """Persist current state after each pass."""
        module.parsing_log = list(self.parsing_log)
        await self.db.commit()

    async def _generate_embeddings(self, module: AdventureModule) -> None:
        """Generate embeddings for semantic search."""
        # Locations
        locations = await self.db.execute(
            select(AdventureLocation).where(AdventureLocation.module_id == module.id)
        )
        for location in locations.scalars():
            text = f"{location.name}\n{location.dm_description}"
            if location.read_aloud_text:
                text += f"\n{location.read_aloud_text}"
            embedding = await self.embedding_service.get_embedding(text)
            location.embedding = embedding

        # NPCs
        npcs = await self.db.execute(
            select(AdventureNPC).where(AdventureNPC.module_id == module.id)
        )
        for npc in npcs.scalars():
            text = f"{npc.name}"
            if npc.title:
                text += f" ({npc.title})"
            if npc.description:
                text += f"\n{npc.description}"
            if npc.personality:
                text += f"\n{npc.personality}"
            embedding = await self.embedding_service.get_embedding(text)
            npc.embedding = embedding

        # Encounters
        encounters = await self.db.execute(
            select(AdventureEncounter).where(AdventureEncounter.module_id == module.id)
        )
        for encounter in encounters.scalars():
            text = f"{encounter.name}"
            if encounter.description:
                text += f"\n{encounter.description}"
            if encounter.creatures:
                creature_names = [c.get("name", "") for c in encounter.creatures]
                text += f"\nCreatures: {', '.join(creature_names)}"
            embedding = await self.embedding_service.get_embedding(text)
            encounter.embedding = embedding

        # Items
        items = await self.db.execute(
            select(AdventureItem).where(AdventureItem.module_id == module.id)
        )
        for item in items.scalars():
            text = f"{item.name}"
            if item.description:
                text += f"\n{item.description}"
            if item.magical_properties:
                text += f"\n{item.magical_properties}"
            embedding = await self.embedding_service.get_embedding(text)
            item.embedding = embedding

        await self.db.flush()

    async def _run_embeddings_only(
        self,
        module: AdventureModule,
        progress_callback: Optional[callable] = None,
    ) -> AdventureModule:
        """Run only embeddings for recovery."""
        try:
            self.parsing_log = []
            self._log(f"Resuming embeddings for module {module.id}")

            await self._update_progress(module, 95, progress_callback)
            await self._generate_embeddings(module)

            await self._update_module_stats(module)
            module.parsing_status = ParsingStatus.COMPLETED
            module.parsing_progress = 100

            self._log("Embeddings complete!")
            await self.db.flush()
            await self._update_progress(module, 100, progress_callback)

            return module

        except Exception as e:
            logger.exception(f"Failed to generate embeddings for {module.id}")
            module.parsing_status = ParsingStatus.FAILED
            module.parsing_error = str(e)
            await self.db.flush()
            raise

    async def _update_module_stats(self, module: AdventureModule) -> None:
        """Update module statistics."""
        # Count entities
        result = await self.db.execute(
            select(func.count(AdventureLocation.id))
            .where(AdventureLocation.module_id == module.id)
        )
        module.location_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(AdventureNPC.id))
            .where(AdventureNPC.module_id == module.id)
        )
        module.npc_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(AdventureEncounter.id))
            .where(AdventureEncounter.module_id == module.id)
        )
        module.encounter_count = result.scalar() or 0

        result = await self.db.execute(
            select(func.count(AdventureItem.id))
            .where(AdventureItem.module_id == module.id)
        )
        module.item_count = result.scalar() or 0

        # Store context data in module if fields exist
        if hasattr(module, 'adventure_flow') and self.context.adventure_flow:
            module.adventure_flow = self.context.adventure_flow

        if hasattr(module, 'critical_path') and self.context.critical_path:
            module.critical_path = self.context.critical_path

        if hasattr(module, 'dm_overview') and self.context.module_dm_guidance:
            module.dm_overview = self.context.module_dm_guidance

        await self.db.flush()


# Convenience function for API usage
async def parse_adventure_multipass(
    db: AsyncSession,
    document_id: UUID,
    progress_callback: Optional[callable] = None,
    embeddings_only: bool = False,
) -> AdventureModule:
    """Parse an adventure module using the multi-pass parser.

    This is the recommended entry point for the new context-aware extraction.
    """
    parser = MultiPassParser(db)
    return await parser.parse_adventure(
        document_id,
        progress_callback=progress_callback,
        embeddings_only=embeddings_only,
    )
