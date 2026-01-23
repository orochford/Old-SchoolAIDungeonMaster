"""Pass 1: Structure & Overview extraction.

This pass establishes high-level understanding before detailed extraction:
- Module metadata (title, levels, background)
- Location list with brief descriptions
- Overall adventure flow/goals
"""

import logging
from typing import Dict, Any

from app.domains.adventures.models import AdventureModule
from app.domains.adventures.extraction_context import (
    ExtractionContext, ModuleOverview, LocationBrief
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS1_OVERVIEW_PROMPT = """You are analyzing a tabletop RPG adventure module to extract its high-level structure.

## YOUR TASK
Extract the following:
1. Module metadata (title, code, levels, summary)
2. Main adventure objectives/goals
3. A list of ALL keyed locations with brief (1-line) descriptions
4. The overall adventure flow (how the adventure progresses)

## IMPORTANT NOTES
- For locations, look for sections titled "ENCOUNTER AREAS", "KEY TO THE LEVEL", etc.
- Each location should have a key (number/letter), name, and brief description
- The adventure flow should describe the intended progression through the adventure
- Main objectives are what players are trying to accomplish

## OUTPUT FORMAT
Respond in JSON format:
```json
{{
  "title": "Adventure Title",
  "code": "B1 or null",
  "level_min": 1,
  "level_max": 3,
  "summary": "2-3 sentence summary of the adventure",
  "main_objectives": ["Find treasure", "Defeat the boss", "Escape alive"],
  "adventure_flow": "Entry -> Upper level exploration -> Discovery of lower level -> Boss/treasure",
  "player_background": "The FULL TEXT of any section titled 'BACKGROUND SHEET', 'BACKGROUND FOR PLAYERS', 'Player Introduction', or similar. This is narrative text meant to be shared with players at adventure start. If a PLAYER BACKGROUND SECTION was extracted above, use that complete text. Include the full section content, not a summary. Return null only if no such section exists.",
  "rumors_table": [{{"roll": "1", "rumor": "...", "is_true": true}}],
  "location_briefs": [
    {{"key": "1", "name": "Alcoves", "brief": "Defensive entry with arrow slits", "level": 1}},
    {{"key": "2", "name": "Kitchen", "brief": "Food preparation area", "level": 1}}
  ]
}}
```

## ADVENTURE TEXT (first 20K characters)
{text}
"""


class OverviewPass(BasePass):
    """Pass 1: Extract module overview and structure."""

    name = "pass1_overview"
    description = "Extract module overview and location list"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Extract overview information.

        Input: First 20K chars + section headers + room list from preprocessing
        Output: Module overview and location briefs
        """
        self._log("Extracting module overview and structure...")
        updates = ExtractionContext()

        # Build input text - first 20K chars plus any section headers
        input_text = full_text[:20000]

        # Add section summary from preprocessing if available
        if preprocessed.get('sections'):
            sections_summary = "\n\n## DOCUMENT SECTIONS IDENTIFIED:\n"
            for name, (start, end) in preprocessed['sections'].items():
                sections_summary += f"- {name}: chars {start}-{end}\n"
            input_text += sections_summary

        # Add preprocessed room count hint
        if preprocessed.get('rooms'):
            rooms_hint = f"\n\n## NOTE: Preprocessor found {len(preprocessed['rooms'])} room entries.\n"
            rooms_hint += "First few rooms: "
            for room in preprocessed['rooms'][:5]:
                rooms_hint += f"{room['location_key']}. {room['name']}, "
            input_text += rooms_hint

        # If preprocessor found a player background section, include it
        if preprocessed.get('player_background_section'):
            input_text += f"\n\n## PLAYER BACKGROUND SECTION (extracted from document):\n"
            input_text += preprocessed['player_background_section'][:4000]  # Limit size

        # Call LLM
        result = await self._call_llm(PASS1_OVERVIEW_PROMPT, input_text, stage_name="pass1_overview")

        if not result:
            self._log("WARNING: No overview data extracted")
            return updates

        # Build ModuleOverview
        updates.overview = ModuleOverview(
            title=result.get('title', module.title or 'Unknown'),
            code=result.get('code'),
            level_min=self._safe_int(result.get('level_min')),
            level_max=self._safe_int(result.get('level_max')),
            summary=result.get('summary', ''),
            main_objectives=result.get('main_objectives', []),
            adventure_flow=result.get('adventure_flow', ''),
        )

        # Store adventure flow
        updates.adventure_flow = result.get('adventure_flow', '')

        # Build location briefs
        location_briefs = result.get('location_briefs', [])

        # If LLM didn't find locations, use preprocessed rooms
        if not location_briefs and preprocessed.get('rooms'):
            self._log("Using preprocessed rooms for location list")
            for room in preprocessed['rooms']:
                updates.location_list.append(LocationBrief(
                    key=room['location_key'],
                    name=room['name'],
                    brief_desc=room.get('start_text', '')[:100],
                    dungeon_level=room.get('dungeon_level', 1),
                ))
        else:
            for loc in location_briefs:
                updates.location_list.append(LocationBrief(
                    key=str(loc.get('key', '')),
                    name=loc.get('name', 'Unknown'),
                    brief_desc=loc.get('brief', ''),
                    dungeon_level=self._safe_int(loc.get('level'), 1),
                ))

        self._log(f"Found {len(updates.location_list)} locations")
        self._log(f"Title: {updates.overview.title}")
        self._log(f"Code: {updates.overview.code or 'N/A'}")
        self._log(f"Objectives: {len(updates.overview.main_objectives)}")

        # Also update the module with metadata
        await self._apply_metadata_to_module(module, result)

        return updates

    async def _apply_metadata_to_module(
        self,
        module: AdventureModule,
        metadata: Dict[str, Any]
    ) -> None:
        """Apply extracted metadata to the AdventureModule."""
        if metadata.get('title'):
            module.title = metadata['title']
        if metadata.get('code'):
            module.code = metadata['code']
        if metadata.get('level_min'):
            module.recommended_level_min = self._safe_int(metadata['level_min'])
        if metadata.get('level_max'):
            module.recommended_level_max = self._safe_int(metadata['level_max'])
        if metadata.get('summary'):
            module.summary = metadata['summary']
        if metadata.get('player_background'):
            module.player_background = metadata['player_background']
        if metadata.get('rumors_table'):
            module.rumors_table = metadata['rumors_table']

        await self.db.flush()
