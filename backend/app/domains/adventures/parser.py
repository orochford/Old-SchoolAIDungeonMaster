"""LLM-powered adventure module parsing service."""

import json
import logging
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.llm.client import ClaudeClient
from app.rag.embeddings import EmbeddingService
from app.domains.sourcebooks.models import PDFDocument, PDFChunk, ExtractedImage
from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, AdventureItem, AdventureStoryBeat,
    ParsingStatus, EncounterType,
)
from app.domains.adventures.prompts import (
    METADATA_EXTRACTION_PROMPT,
    LOCATION_SEGMENTATION_PROMPT,
    LOCATION_EXTRACTION_PROMPT,
    NPC_EXTRACTION_PROMPT,
    ENCOUNTER_EXTRACTION_PROMPT,
    ITEM_EXTRACTION_PROMPT,
    STORY_FLOW_PROMPT,
)
from app.domains.adventures.preprocessor import AdventurePreprocessor

logger = logging.getLogger(__name__)


class AdventureParser:
    """Multi-stage LLM parsing pipeline for adventure modules."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.client = ClaudeClient()
        self.embedding_service = EmbeddingService()
        self.preprocessor = AdventurePreprocessor()
        self.parsing_log: List[str] = []

    def _log(self, message: str) -> None:
        """Add a message to the parsing log."""
        logger.info(message)
        self.parsing_log.append(message)

    def _safe_int(self, value: Any, default: Optional[int] = None) -> Optional[int]:
        """Safely convert a value to int, returning default if not possible."""
        if value is None:
            return default
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            # Try to extract a number from the start of the string
            import re
            match = re.search(r'^-?\d+', str(value).strip())
            if match:
                return int(match.group())
        return default

    async def parse_adventure(
        self,
        document_id: UUID,
        progress_callback: Optional[callable] = None,
        embeddings_only: bool = False,
    ) -> AdventureModule:
        """Parse an adventure module PDF into structured data.

        Args:
            document_id: UUID of the PDFDocument to parse
            progress_callback: Optional callback for progress updates (0-100)
            embeddings_only: If True, skip LLM extraction and only generate embeddings

        Returns:
            The created AdventureModule with all parsed data
        """
        # Get the document and its chunks
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
            # Just regenerate embeddings
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
            # Clear existing data
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
            # Reset parsing log
            self.parsing_log = []
            self._log(f"Starting adventure parsing for document {document_id}")

            # Get all document text
            full_text = await self._get_document_text(document_id)

            if not full_text:
                raise ValueError("No text content found in document")

            self._log(f"Extracted {len(full_text)} characters from {document.original_filename}")

            # Preprocess document to identify structure
            self._log("Preprocessing document structure...")
            preprocessed = self.preprocessor.preprocess(full_text)
            self._log(f"  → Preprocessor found {len(preprocessed['rooms'])} rooms")
            self._log(f"  → Preprocessor found {len(preprocessed['wandering_tables'])} wandering tables")

            # Stage 1: Extract metadata (10%)
            self._log("Stage 1/9: Extracting module metadata...")
            await self._update_progress(module, 5, progress_callback)
            metadata = await self._extract_metadata(full_text[:50000])  # First ~50k chars
            await self._apply_metadata(module, metadata)
            self._log(f"  → Title: {module.title}")
            self._log(f"  → Code: {module.code or 'N/A'}")
            self._log(f"  → Levels: {module.recommended_level_min}-{module.recommended_level_max}")
            await self._update_progress(module, 10, progress_callback)

            # Stage 2: Identify locations (20%)
            self._log("Stage 2/9: Identifying locations...")
            await self._update_progress(module, 15, progress_callback)

            # Use preprocessed rooms if available, otherwise fall back to LLM
            if preprocessed['rooms']:
                location_segments = preprocessed['rooms']
                self._log(f"  → Using {len(location_segments)} preprocessed room segments")
            else:
                self._log("  → No preprocessed rooms, falling back to LLM segmentation")
                location_segments = await self._segment_locations(full_text)
                self._log(f"  → LLM found {len(location_segments)} location segments")
            await self._update_progress(module, 20, progress_callback)

            # Stage 3: Parse locations in batches (40%)
            self._log("Stage 3/9: Parsing location details...")
            await self._parse_locations(module, full_text, location_segments, progress_callback)
            await self._update_progress(module, 40, progress_callback)

            # Stage 4: Extract NPCs (55%)
            self._log("Stage 4/9: Extracting NPCs...")
            await self._update_progress(module, 45, progress_callback)
            await self._extract_npcs(module, full_text)
            await self._update_progress(module, 55, progress_callback)

            # Stage 5: Extract encounters (70%)
            self._log("Stage 5/9: Extracting encounters...")
            await self._update_progress(module, 60, progress_callback)

            # Use preprocessed wandering tables if available, otherwise let LLM extract all
            has_preprocessed_wandering = bool(preprocessed['wandering_tables'])
            if has_preprocessed_wandering:
                self._log(f"  → Saving {len(preprocessed['wandering_tables'])} preprocessed wandering tables")
                await self._save_wandering_encounters(module, preprocessed['wandering_tables'])
            else:
                self._log("  → No preprocessed wandering tables, LLM will extract all encounters")

            # Extract encounters via LLM (skip wandering only if preprocessor handled them)
            await self._extract_encounters(module, full_text, skip_wandering=has_preprocessed_wandering)
            await self._update_progress(module, 70, progress_callback)

            # Stage 6: Extract items (80%)
            self._log("Stage 6/9: Extracting items...")
            await self._update_progress(module, 72, progress_callback)
            await self._extract_items(module, full_text)
            await self._update_progress(module, 78, progress_callback)

            # Stage 7: Link images and maps (85%)
            self._log("Stage 7/9: Linking maps and atmosphere images...")
            await self._update_progress(module, 80, progress_callback)
            await self._link_images(module, document_id)
            await self._update_progress(module, 85, progress_callback)

            # Stage 8: Analyze story flow (92%)
            self._log("Stage 8/9: Analyzing story flow...")
            await self._update_progress(module, 87, progress_callback)
            await self._extract_story_beats(module, full_text)
            await self._update_progress(module, 92, progress_callback)

            # Stage 9: Generate embeddings (100%)
            self._log("Stage 9/9: Generating search embeddings...")
            await self._update_progress(module, 95, progress_callback)
            await self._generate_embeddings(module)

            # Update final stats
            await self._update_module_stats(module)

            # Verify extraction quality
            verification_issues = self._verify_extraction(
                module,
                preprocessed,
                location_segments,
            )
            if verification_issues:
                self._log("Verification warnings:")
                for issue in verification_issues:
                    self._log(f"  ⚠ {issue}")

            module.parsing_status = ParsingStatus.COMPLETED
            module.parsing_progress = 100

            self._log("Parsing complete!")
            self._log(f"  → {module.location_count} locations")
            self._log(f"  → {module.npc_count} NPCs")
            self._log(f"  → {module.encounter_count} encounters")
            self._log(f"  → {module.item_count} items")
            if verification_issues:
                self._log(f"  → {len(verification_issues)} verification warnings (see above)")

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
        """Get all text from document, preferring markdown file if available.

        Uses the pymupdf4llm markdown export which preserves table formatting
        better than rejoining semantic chunks.
        """
        import os

        # First check if we have a markdown file
        result = await self.db.execute(
            select(PDFDocument).where(PDFDocument.id == document_id)
        )
        document = result.scalar_one_or_none()

        if document and document.markdown_path and os.path.exists(document.markdown_path):
            try:
                with open(document.markdown_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    logger.info(f"Using markdown file for parsing: {document.markdown_path} ({len(content)} chars)")
                    return content
            except Exception as e:
                logger.warning(f"Failed to read markdown file, falling back to chunks: {e}")

        # Fall back to joining chunks
        result = await self.db.execute(
            select(PDFChunk)
            .where(PDFChunk.document_id == document_id)
            .order_by(PDFChunk.chunk_index)
        )
        chunks = list(result.scalars().all())
        logger.info(f"Using {len(chunks)} chunks for parsing (no markdown file available)")
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
        """Update parsing progress and save log for live updates."""
        module.parsing_progress = progress
        module.parsing_log = list(self.parsing_log)  # Copy log for live updates
        await self.db.commit()  # Commit so other connections can see updates
        if callback:
            callback(progress)

    def _sanitize_text(self, text: str) -> str:
        """Sanitize text for LLM processing."""
        import re
        # Remove null bytes and other problematic characters
        text = text.replace('\x00', '')
        # Replace multiple whitespace with single space (but keep newlines)
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Remove very long sequences of repeated characters
        text = re.sub(r'(.)\1{20,}', r'\1\1\1', text)
        return text

    async def _call_llm(
        self,
        prompt: str,
        text: str,
        max_retries: int = 2,
        stage_name: str = "unknown"
    ) -> Dict[str, Any]:
        """Call the LLM and parse JSON response with retry logic.

        Uses the configured processing AI provider (Claude or OpenAI).
        No fallback - respects user's provider choice.

        Args:
            prompt: The prompt template (with {text} placeholder)
            text: The adventure text to analyze
            max_retries: Number of retry attempts
            stage_name: Name of parsing stage for logging
        """
        import anthropic
        import openai
        from app.config import settings

        # Sanitize and limit input text
        clean_text = self._sanitize_text(text[:100000])

        # Check if prompt uses {text} or other placeholders
        if "{text}" in prompt:
            formatted_prompt = prompt.format(text=clean_text)
        else:
            # Prompt may have other placeholders, append text at end
            formatted_prompt = prompt + f"\n\nText to analyze:\n{clean_text}"

        system_prompt = ("You are a precise data extractor for tabletop RPG adventure modules. "
                        "CRITICAL: Always respond with valid JSON only. "
                        "Your response must start with { and end with }. "
                        "No markdown code blocks, no explanation text, just the JSON object.")

        logger.info(f"[{stage_name}] Starting LLM call (text length: {len(clean_text)} chars)")
        logger.info(f"[{stage_name}] Provider: {settings.processing_provider}")

        # Use configured provider only - no fallback
        if settings.processing_provider == "openai":
            result = await self._call_openai(formatted_prompt, system_prompt, max_retries, stage_name, settings)
        else:
            result = await self._call_claude(formatted_prompt, system_prompt, max_retries, stage_name)

        if result is not None:
            return result

        logger.error(f"[{stage_name}] LLM call failed")
        return {}

    async def _call_claude(
        self,
        formatted_prompt: str,
        system_prompt: str,
        max_retries: int,
        stage_name: str,
    ) -> Optional[Dict[str, Any]]:
        """Call Claude API with retries using processing settings."""
        import anthropic
        from app.config import settings

        model = settings.processing_claude_model or "claude-haiku-4-5-20250101"
        self._log(f"  → Using Claude ({model})...")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"[{stage_name}] Attempt {attempt + 1}/{max_retries + 1} (Claude: {model})")

                # Use direct Anthropic client with processing model
                client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
                response = await client.messages.create(
                    model=model,
                    messages=[{"role": "user", "content": formatted_prompt}],
                    system=system_prompt,
                    max_tokens=8192,
                )

                # Extract JSON from response
                content = ""
                if response.content:
                    for block in response.content:
                        if hasattr(block, 'text'):
                            content = block.text
                            break

                if not content:
                    logger.warning(f"[{stage_name}] Empty response from Claude")
                    continue

                logger.debug(f"[{stage_name}] Claude response (first 500 chars): {content[:500]}")

                parsed = self._extract_json(content, stage_name)
                if parsed is not None:
                    logger.info(f"[{stage_name}] Successfully parsed JSON from Claude")
                    return parsed

            except anthropic.AuthenticationError as e:
                self._log(f"ERROR: Claude API authentication failed")
                logger.error(f"[{stage_name}] Claude auth error: {e}")
                return None
            except anthropic.RateLimitError as e:
                self._log(f"ERROR: Claude API rate limit exceeded")
                logger.error(f"[{stage_name}] Claude rate limit: {e}")
                return None
            except anthropic.APIStatusError as e:
                if "credit" in str(e).lower() or "billing" in str(e).lower():
                    self._log(f"ERROR: Claude API credits exhausted")
                    logger.error(f"[{stage_name}] Claude credit error: {e}")
                    return None
                last_error = e
                logger.warning(f"[{stage_name}] Claude API error (attempt {attempt + 1}): {e}")
            except Exception as e:
                last_error = e
                logger.warning(f"[{stage_name}] Claude call failed (attempt {attempt + 1}): {e}")

        if last_error:
            logger.error(f"[{stage_name}] Claude all attempts failed. Last error: {last_error}")
        return None

    async def _call_openai(
        self,
        formatted_prompt: str,
        system_prompt: str,
        max_retries: int,
        stage_name: str,
        settings,
    ) -> Optional[Dict[str, Any]]:
        """Call OpenAI API with retries."""
        import openai

        if not settings.openai_api_key:
            self._log(f"ERROR: No OpenAI API key configured")
            return None

        model = settings.processing_openai_model or "gpt-4o-mini"
        self._log(f"  → Using OpenAI ({model})...")

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                logger.info(f"[{stage_name}] Attempt {attempt + 1}/{max_retries + 1} (OpenAI: {model})")

                client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

                response = await client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": formatted_prompt}
                    ],
                )

                content = response.choices[0].message.content
                if not content:
                    logger.warning(f"[{stage_name}] Empty response from OpenAI")
                    continue

                logger.debug(f"[{stage_name}] OpenAI response (first 500 chars): {content[:500]}")

                parsed = self._extract_json(content, stage_name)
                if parsed is not None:
                    logger.info(f"[{stage_name}] Successfully parsed JSON from OpenAI")
                    return parsed

            except Exception as e:
                last_error = e
                logger.warning(f"[{stage_name}] OpenAI call failed (attempt {attempt + 1}): {e}")

        if last_error:
            self._log(f"ERROR: OpenAI failed: {str(last_error)[:100]}")
            logger.error(f"[{stage_name}] OpenAI all attempts failed. Last error: {last_error}")
        return None

    def _extract_json(self, content: str, stage_name: str) -> Optional[Dict[str, Any]]:
        """Extract and parse JSON from LLM response with multiple strategies."""
        import re

        # Strategy 1: Clean up and try direct parse
        content = content.strip()

        # Remove markdown code blocks
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        # Strategy 2: Try direct parse first
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Strategy 3: Find JSON object with balanced braces
        brace_start = content.find('{')
        if brace_start == -1:
            logger.warning(f"[{stage_name}] No opening brace found in response")
            # Try to construct JSON if we see key patterns
            if '"title"' in content or '"locations"' in content or '"npcs"' in content:
                logger.warning(f"[{stage_name}] Found JSON keys without brace, attempting to wrap")
                content = '{' + content
                if not content.rstrip().endswith('}'):
                    content = content.rstrip() + '}'

        # Find matching closing brace
        brace_start = content.find('{')
        if brace_start != -1:
            depth = 0
            brace_end = -1
            for i, c in enumerate(content[brace_start:], start=brace_start):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        brace_end = i
                        break

            if brace_end != -1:
                json_str = content[brace_start:brace_end + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError as e:
                    logger.debug(f"[{stage_name}] Balanced brace extraction failed: {e}")

                    # Strategy 4: Fix common JSON issues
                    fixed = self._fix_json(json_str)
                    try:
                        return json.loads(fixed)
                    except json.JSONDecodeError:
                        pass

        # Strategy 5: Use regex as last resort
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                fixed = self._fix_json(json_match.group(0))
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError as e:
                    logger.warning(f"[{stage_name}] All JSON extraction strategies failed: {e}")

        return None

    def _fix_json(self, content: str) -> str:
        """Attempt to fix common JSON formatting issues."""
        import re

        # Remove trailing commas before } or ]
        content = re.sub(r',(\s*[}\]])', r'\1', content)

        # Fix unquoted keys
        content = re.sub(r'(\{|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'\1"\2":', content)

        # Fix single quotes used instead of double quotes for strings
        # Be careful not to break apostrophes in text
        # Only fix obvious cases: 'key': or ': 'value'
        content = re.sub(r":\s*'([^']*)'(\s*[,}\]])", r': "\1"\2', content)

        # Remove control characters except newlines and tabs
        content = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', content)

        return content

    async def _extract_metadata(self, text: str) -> Dict[str, Any]:
        """Extract module metadata."""
        return await self._call_llm(METADATA_EXTRACTION_PROMPT, text, stage_name="metadata")

    async def _apply_metadata(self, module: AdventureModule, metadata: Dict[str, Any]) -> None:
        """Apply extracted metadata to the module."""
        if metadata.get("title"):
            module.title = metadata["title"]
        if metadata.get("code"):
            module.code = metadata["code"]
        if metadata.get("recommended_level_min"):
            module.recommended_level_min = metadata["recommended_level_min"]
        if metadata.get("recommended_level_max"):
            module.recommended_level_max = metadata["recommended_level_max"]
        if metadata.get("recommended_party_size_min"):
            module.recommended_party_size_min = metadata["recommended_party_size_min"]
        if metadata.get("recommended_party_size_max"):
            module.recommended_party_size_max = metadata["recommended_party_size_max"]
        if metadata.get("summary"):
            module.summary = metadata["summary"]
        if metadata.get("player_background"):
            module.player_background = metadata["player_background"]
        if metadata.get("rumors_table"):
            module.rumors_table = metadata["rumors_table"]

        await self.db.flush()

    async def _segment_locations(self, text: str) -> List[Dict[str, Any]]:
        """Identify location boundaries in the text."""
        result = await self._call_llm(LOCATION_SEGMENTATION_PROMPT, text, stage_name="location_segmentation")
        return result.get("locations", [])

    async def _parse_locations(
        self,
        module: AdventureModule,
        full_text: str,
        segments: List[Dict[str, Any]],
        progress_callback: Optional[callable] = None,
    ) -> None:
        """Parse individual locations from segments."""
        if not segments:
            return

        # Build location lookup for parent relationships
        location_ids: Dict[str, UUID] = {}

        # Process in batches of 5
        batch_size = 5
        total = len(segments)
        parsed_count = 0

        for i in range(0, total, batch_size):
            batch = segments[i:i + batch_size]

            for segment in batch:
                location_key = segment.get("location_key", "")
                location_name = segment.get("name", "Unknown")

                # Find the relevant text for this location
                location_text = self._extract_location_text(full_text, segment)

                # Parse the location
                prompt = LOCATION_EXTRACTION_PROMPT.format(
                    location_key=location_key,
                    location_name=location_name,
                    text=location_text,
                )
                data = await self._call_llm(prompt, location_text, stage_name=f"location_{location_key}")

                if not data:
                    self._log(f"  → Skipped {location_key} (no data extracted)")
                    continue

                # Determine parent
                parent_id = None
                parent_key = segment.get("parent_key")
                if parent_key and parent_key in location_ids:
                    parent_id = location_ids[parent_key]

                # Get values with fallbacks for None
                loc_name = data.get("name") or location_name or f"Location {location_key}"
                loc_desc = data.get("dm_description") or segment.get("start_text") or "No description available."

                # Create location
                location = AdventureLocation(
                    module_id=module.id,
                    location_key=location_key or str(len(location_ids) + 1),
                    name=loc_name,
                    dm_description=loc_desc,
                    read_aloud_text=data.get("read_aloud_text"),
                    features=data.get("features") or [],
                    exits=data.get("exits") or {},
                    traps=data.get("traps") or [],
                    secrets=data.get("secrets") or [],
                    treasure=data.get("treasure") or [],
                    dungeon_level=self._safe_int(data.get("dungeon_level"), 1),
                    tier=data.get("tier"),
                    parent_location_id=parent_id,
                )
                self.db.add(location)
                await self.db.flush()

                location_ids[location_key] = location.id
                parsed_count += 1
                self._log(f"  → [{parsed_count}/{total}] {loc_name}")

            # Update progress and commit for live updates
            progress = 20 + int(20 * min(i + batch_size, total) / total)
            await self._update_progress(module, progress, progress_callback)

    def _extract_location_text(self, full_text: str, segment: Dict[str, Any]) -> str:
        """Extract the text for a specific location."""
        start_text = segment.get("start_text", "")
        if not start_text:
            return full_text[:10000]

        # Find the start position
        start_pos = full_text.find(start_text)
        if start_pos == -1:
            # Try fuzzy match
            start_pos = 0

        # Extract ~5000 characters starting from this position
        return full_text[start_pos:start_pos + 5000]

    async def _extract_npcs(self, module: AdventureModule, text: str) -> None:
        """Extract NPCs from the adventure."""
        result = await self._call_llm(NPC_EXTRACTION_PROMPT, text, stage_name="npc_extraction")
        npcs = result.get("npcs", [])
        self._log(f"  → Found {len(npcs)} NPCs")

        for npc_data in npcs:
            # Find location if referenced
            location_id = None
            location_key = npc_data.get("location_key")
            if location_key:
                loc_result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module.id)
                    .where(AdventureLocation.location_key == location_key)
                )
                location = loc_result.scalar_one_or_none()
                if location:
                    location_id = location.id

            npc = AdventureNPC(
                module_id=module.id,
                location_id=location_id,
                name=npc_data.get("name", "Unknown"),
                title=npc_data.get("title"),
                description=npc_data.get("description"),
                appearance=npc_data.get("appearance"),
                personality=npc_data.get("personality"),
                motivation=npc_data.get("motivation"),
                goals=npc_data.get("goals", []),
                dialogue_hooks=npc_data.get("dialogue_hooks", []),
                stats=npc_data.get("stats", {}),
                equipment=npc_data.get("equipment", []),
                treasure=npc_data.get("treasure", []),
                spells=npc_data.get("spells", []),
                faction=npc_data.get("faction"),
                initial_disposition=npc_data.get("initial_disposition", "neutral"),
                is_unique=npc_data.get("is_unique", True),
            )
            self.db.add(npc)

        await self.db.flush()

    async def _save_wandering_encounters(
        self,
        module: AdventureModule,
        wandering_tables: List[Dict[str, Any]]
    ) -> None:
        """Save preprocessed wandering monster tables as encounters."""
        total_entries = 0

        for table in wandering_tables:
            table_name = table.get('table_name', 'Wandering Monsters')
            die_roll = table.get('die_roll', '1d6')
            check_freq = table.get('check_frequency')
            level = table.get('dungeon_level', 1)

            for entry in table.get('entries', []):
                # Build creatures list from entry
                creatures = entry.get('creatures', [])
                if not creatures and entry.get('name'):
                    # Create creature entry from basic info
                    creatures = [{
                        'name': entry.get('name', 'Unknown'),
                        'count': entry.get('count', '1'),
                    }]

                encounter = AdventureEncounter(
                    module_id=module.id,
                    location_id=None,
                    encounter_type=EncounterType.WANDERING,
                    wandering_table_name=f"{table_name} (Level {level})",
                    die_roll=die_roll,
                    roll_range=entry.get('roll_range'),
                    check_frequency=check_freq,
                    name=entry.get('name', 'Wandering Monster'),
                    description=entry.get('description'),
                    creatures=creatures,
                    tactics=None,
                    treasure=[],
                    xp_value=self._safe_int(creatures[0].get('xp') if creatures else None),
                )
                self.db.add(encounter)
                total_entries += 1

        await self.db.flush()
        self._log(f"  → Saved {total_entries} wandering monster entries")

    async def _extract_encounters(self, module: AdventureModule, text: str, skip_wandering: bool = False) -> None:
        """Extract encounters (fixed and optionally wandering) from the adventure."""
        result = await self._call_llm(ENCOUNTER_EXTRACTION_PROMPT, text, stage_name="encounter_extraction")
        encounters = result.get("encounters", [])

        # Filter out wandering if already handled by preprocessor
        if skip_wandering:
            encounters = [e for e in encounters if e.get("encounter_type") != "wandering"]
            self._log(f"  → LLM found {len(encounters)} fixed encounters (wandering skipped)")
        else:
            fixed = sum(1 for e in encounters if e.get("encounter_type") != "wandering")
            wandering = len(encounters) - fixed
            self._log(f"  → Found {fixed} fixed encounters, {wandering} wandering encounters")

        for enc_data in encounters:
            # Find location if referenced
            location_id = None
            location_key = enc_data.get("location_key")
            if location_key:
                loc_result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module.id)
                    .where(AdventureLocation.location_key == location_key)
                )
                location = loc_result.scalar_one_or_none()
                if location:
                    location_id = location.id

            enc_type = EncounterType.WANDERING if enc_data.get("encounter_type") == "wandering" else EncounterType.FIXED

            encounter = AdventureEncounter(
                module_id=module.id,
                location_id=location_id,
                encounter_type=enc_type,
                wandering_table_name=enc_data.get("wandering_table_name"),
                die_roll=enc_data.get("die_roll"),
                roll_range=enc_data.get("roll_range"),
                check_frequency=enc_data.get("check_frequency"),
                name=enc_data.get("name") or "Encounter",
                description=enc_data.get("description"),
                creatures=enc_data.get("creatures") or [],
                tactics=enc_data.get("tactics"),
                treasure=enc_data.get("treasure") or [],
                xp_value=self._safe_int(enc_data.get("xp_value")),
                trigger_condition=enc_data.get("trigger_condition"),
            )
            self.db.add(encounter)

        await self.db.flush()

    async def _extract_items(self, module: AdventureModule, text: str) -> None:
        """Extract notable items from the adventure."""
        result = await self._call_llm(ITEM_EXTRACTION_PROMPT, text, stage_name="item_extraction")
        items = result.get("items", [])
        magical = sum(1 for i in items if i.get("is_magical"))
        self._log(f"  → Found {len(items)} items ({magical} magical)")

        for item_data in items:
            # Find location if referenced
            location_id = None
            location_key = item_data.get("location_key")
            if location_key:
                loc_result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module.id)
                    .where(AdventureLocation.location_key == location_key)
                )
                location = loc_result.scalar_one_or_none()
                if location:
                    location_id = location.id

            item = AdventureItem(
                module_id=module.id,
                location_id=location_id,
                name=item_data.get("name") or "Unknown Item",
                item_type=item_data.get("item_type"),
                description=item_data.get("description"),
                value=item_data.get("value"),
                is_magical=bool(item_data.get("is_magical", False)),
                magical_properties=item_data.get("magical_properties"),
                charges=self._safe_int(item_data.get("charges")),
                is_key_item=bool(item_data.get("is_key_item", False)),
                found_at=item_data.get("found_at"),
            )
            self.db.add(item)

        await self.db.flush()

    async def _extract_story_beats(self, module: AdventureModule, text: str) -> None:
        """Extract story progression beats from the adventure."""
        result = await self._call_llm(STORY_FLOW_PROMPT, text, stage_name="story_flow")
        beats = result.get("story_beats", [])
        self._log(f"  → Found {len(beats)} story beats")

        for idx, beat_data in enumerate(beats):
            beat = AdventureStoryBeat(
                module_id=module.id,
                name=beat_data.get("name") or "Story Beat",
                sequence=self._safe_int(beat_data.get("sequence"), idx),
                description=beat_data.get("description"),
                trigger=beat_data.get("trigger"),
                branches=beat_data.get("branches") or [],
                related_locations=beat_data.get("related_locations") or [],
                is_critical_path=bool(beat_data.get("is_critical_path", False)),
            )
            self.db.add(beat)

        await self.db.flush()

    async def _generate_embeddings(self, module: AdventureModule) -> None:
        """Generate embeddings for semantic search."""
        # Generate embeddings for locations
        locations = await self.db.execute(
            select(AdventureLocation).where(AdventureLocation.module_id == module.id)
        )
        for location in locations.scalars():
            text = f"{location.name}\n{location.dm_description}"
            if location.read_aloud_text:
                text += f"\n{location.read_aloud_text}"
            embedding = await self.embedding_service.get_embedding(text)
            location.embedding = embedding

        # Generate embeddings for NPCs
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

        # Generate embeddings for encounters
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

        # Generate embeddings for items
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
        """Run only the embeddings stage for a module that failed at that step."""
        try:
            self.parsing_log = []
            self._log(f"Resuming embeddings generation for module {module.id}")

            self._log("Stage 8/8: Generating search embeddings...")
            await self._update_progress(module, 95, progress_callback)
            await self._generate_embeddings(module)

            # Update final stats
            await self._update_module_stats(module)
            module.parsing_status = ParsingStatus.COMPLETED
            module.parsing_progress = 100

            self._log("Embeddings complete!")
            self._log(f"  → {module.location_count} locations")
            self._log(f"  → {module.npc_count} NPCs")
            self._log(f"  → {module.encounter_count} encounters")
            self._log(f"  → {module.item_count} items")

            await self.db.flush()
            await self._update_progress(module, 100, progress_callback)

            return module

        except Exception as e:
            logger.exception(f"Failed to generate embeddings for module {module.id}")
            module.parsing_status = ParsingStatus.FAILED
            module.parsing_error = str(e)
            await self.db.flush()
            raise

    async def _update_module_stats(self, module: AdventureModule) -> None:
        """Update module statistics."""
        from sqlalchemy import func

        # Count locations
        result = await self.db.execute(
            select(func.count(AdventureLocation.id))
            .where(AdventureLocation.module_id == module.id)
        )
        module.location_count = result.scalar() or 0

        # Count NPCs
        result = await self.db.execute(
            select(func.count(AdventureNPC.id))
            .where(AdventureNPC.module_id == module.id)
        )
        module.npc_count = result.scalar() or 0

        # Count encounters
        result = await self.db.execute(
            select(func.count(AdventureEncounter.id))
            .where(AdventureEncounter.module_id == module.id)
        )
        module.encounter_count = result.scalar() or 0

        # Count items
        result = await self.db.execute(
            select(func.count(AdventureItem.id))
            .where(AdventureItem.module_id == module.id)
        )
        module.item_count = result.scalar() or 0

        await self.db.flush()

    def _verify_extraction(
        self,
        module: AdventureModule,
        preprocessed: Dict[str, Any],
        location_segments: List[Dict[str, Any]],
    ) -> List[str]:
        """Verify extraction results and return list of issues/warnings.

        Compares actual extracted counts against expected counts from
        preprocessing and input segments.
        """
        issues = []

        # Expected counts
        expected_rooms = len(preprocessed.get('rooms', []))
        expected_wandering_entries = sum(
            len(t.get('entries', []))
            for t in preprocessed.get('wandering_tables', [])
        )
        input_segments = len(location_segments)

        # Check location extraction
        if input_segments > 0:
            extraction_rate = module.location_count / input_segments
            if extraction_rate < 0.5:
                issues.append(
                    f"Low location extraction rate: {module.location_count}/{input_segments} "
                    f"({extraction_rate:.0%}) - many locations may have failed to parse"
                )
            elif extraction_rate < 0.8:
                issues.append(
                    f"Some locations may be missing: {module.location_count}/{input_segments} "
                    f"({extraction_rate:.0%})"
                )

        if module.location_count == 0 and input_segments > 0:
            issues.append(
                f"CRITICAL: No locations extracted despite {input_segments} input segments"
            )

        # Check encounter extraction
        if module.encounter_count == 0:
            if expected_wandering_entries > 0:
                issues.append(
                    f"No encounters extracted (expected at least {expected_wandering_entries} wandering)"
                )
            else:
                issues.append("No encounters extracted - document may lack encounter data")

        # Check for suspiciously low counts in larger documents
        if expected_rooms > 20 and module.location_count < 10:
            issues.append(
                f"Preprocessor found {expected_rooms} rooms but only {module.location_count} extracted"
            )

        # Log verification to debug log
        logger.info(
            f"Extraction verification: "
            f"locations={module.location_count}/{input_segments}, "
            f"encounters={module.encounter_count}, "
            f"npcs={module.npc_count}, "
            f"items={module.item_count}, "
            f"issues={len(issues)}"
        )

        return issues

    async def _link_images(self, module: AdventureModule, document_id: UUID) -> None:
        """Link extracted images (maps, illustrations) to module and locations.

        - Maps and illustrations are stored at module level
        - Locations are linked to nearby images by page proximity
        """
        # Fetch all extracted images for this document
        result = await self.db.execute(
            select(ExtractedImage)
            .where(ExtractedImage.document_id == document_id)
            .order_by(ExtractedImage.page_number)
        )
        images = list(result.scalars().all())

        if not images:
            self._log("  → No extracted images found for this document")
            return

        # Categorize images
        maps = []
        illustrations = []

        for img in images:
            img_data = {
                "image_id": str(img.id),
                "image_type": img.image_type,
                "page": img.page_number,
                "title": img.title or f"{img.image_type.title()} (Page {img.page_number})",
                "path": img.image_path,
                "is_color": img.is_color,
                "width": img.width,
                "height": img.height,
            }

            if img.image_type == "map":
                maps.append(img_data)
            elif img.image_type in ("illustration", "cover"):
                illustrations.append(img_data)

        # Store at module level
        module.maps = maps
        module.illustrations = illustrations

        self._log(f"  → Found {len(maps)} maps, {len(illustrations)} illustrations")

        # Get all locations for this module
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module.id)
        )
        locations = list(result.scalars().all())

        if not locations:
            return

        # Build page -> image mapping for proximity linking
        map_by_page = {img["page"]: img for img in maps if img.get("page")}
        illust_by_page = {img["page"]: img for img in illustrations if img.get("page")}

        # Link locations to nearby images
        linked_count = 0
        for location in locations:
            # Try to determine location's source page
            # For now, use dungeon_level as a rough proxy (level 1 = early pages, etc.)
            # A more sophisticated approach would track source_page during parsing
            loc_page = location.source_page

            if loc_page is None:
                # Estimate page from location key (room 1-20 likely early, 21-40 mid, etc.)
                try:
                    room_num = int(location.location_key)
                    # Rough heuristic: ~2 rooms per page
                    loc_page = max(1, room_num // 2 + 5)  # Offset for intro pages
                except (ValueError, TypeError):
                    loc_page = 10  # Default to mid-document

            # Find nearest map (within 5 pages)
            nearest_map = self._find_nearest_image(loc_page, map_by_page, max_distance=5)
            if nearest_map:
                location.map_image_id = UUID(nearest_map["image_id"])
                linked_count += 1

            # Find nearby illustrations for atmosphere (within 3 pages)
            atmosphere = []
            for page, img in illust_by_page.items():
                if page and abs(page - loc_page) <= 3:
                    relevance = "primary" if abs(page - loc_page) <= 1 else "nearby"
                    atmosphere.append({
                        "image_id": img["image_id"],
                        "relevance": relevance,
                    })

            if atmosphere:
                location.atmosphere_images = atmosphere[:3]  # Max 3 atmosphere images

        await self.db.flush()
        self._log(f"  → Linked {linked_count} locations to maps")

    def _find_nearest_image(
        self,
        target_page: int,
        images_by_page: Dict[int, Dict],
        max_distance: int = 5
    ) -> Optional[Dict]:
        """Find the nearest image to a target page within max_distance."""
        if not images_by_page:
            return None

        nearest = None
        min_distance = max_distance + 1

        for page, img in images_by_page.items():
            if page is None:
                continue
            distance = abs(page - target_page)
            if distance < min_distance:
                min_distance = distance
                nearest = img

        return nearest if min_distance <= max_distance else None
