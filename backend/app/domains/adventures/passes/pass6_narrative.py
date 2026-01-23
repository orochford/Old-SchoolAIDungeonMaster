"""Pass 6: Narrative & Connections extraction.

This pass understands story flow and location relationships:
- Story beats and progression
- Location connections and flow
- Branching paths
- Critical path identification
"""

import logging
from typing import Dict, Any, List

from app.domains.adventures.models import AdventureModule, AdventureStoryBeat
from app.domains.adventures.extraction_context import (
    ExtractionContext, StoryBeat, LocationConnection
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS6_NARRATIVE_PROMPT = """You are analyzing the narrative structure of a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Analyze the adventure's story flow and connections:

### STORY BEATS
Key progression points in the adventure:
- Entry points and hooks
- Key discoveries or revelations
- Boss encounters or climactic moments
- Decision points that branch the story
- Resolution conditions

### LOCATION CONNECTIONS
How locations connect narratively and physically:
- Physical connections (doors, passages, stairs)
- Narrative connections (clues pointing to other areas)
- One-way connections (traps, slides, teleports)
- Secret connections

### CRITICAL PATH
The minimum locations/events needed to complete the adventure.

### RECOMMENDED PATH
A good order for a satisfying experience.

## OUTPUT FORMAT
```json
{{
  "story_beats": [
    {{
      "name": "Entering the Dungeon",
      "sequence": 1,
      "description": "Players discover and enter the main entrance",
      "trigger": {{"type": "location", "value": "1"}},
      "branches": [
        {{"condition": "Enter through front", "next_beat": "Upper Level Exploration", "consequence": "Normal entry"}},
        {{"condition": "Find secret entrance", "next_beat": "Lower Level Shortcut", "consequence": "Skip upper level"}}
      ],
      "related_locations": ["1", "2"],
      "is_critical_path": true
    }}
  ],
  "connections": [
    {{
      "from_location": "1",
      "to_location": "2",
      "connection_type": "passage",
      "description": "Wide corridor",
      "requirements": null
    }},
    {{
      "from_location": "15",
      "to_location": "38",
      "connection_type": "secret",
      "description": "Hidden door behind tapestry",
      "requirements": "Search check DC 15"
    }}
  ],
  "location_flow": {{
    "recommended_path": ["1", "2-14", "30", "lower_level"],
    "shortcuts": [{{"from": "50", "to": "lower_level", "type": "trap"}}],
    "dead_ends": ["20"]
  }},
  "critical_path": ["1", "30", "38", "54"]
}}
```

## TEXT TO ANALYZE
{text}
"""


class NarrativePass(BasePass):
    """Pass 6: Extract narrative structure and connections."""

    name = "pass6_narrative"
    description = "Extract story flow and connections"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Extract narrative structure.

        Input: Full context
        Output: Story beats, connections, critical path
        """
        self._log("Analyzing narrative structure...")
        updates = ExtractionContext()

        # Build comprehensive context
        context_prompt = context.to_context_prompt([
            'overview', 'locations_full', 'encounters', 'npcs', 'dm_notes'
        ])

        # Call LLM
        prompt = PASS6_NARRATIVE_PROMPT.replace("{context}", context_prompt)
        result = await self._call_llm(prompt, full_text, stage_name="pass6_narrative")

        if not result:
            self._log("WARNING: No narrative data extracted")
            return updates

        # Process story beats
        story_beats = result.get('story_beats', [])
        self._log(f"Found {len(story_beats)} story beats")

        for idx, beat_data in enumerate(story_beats):
            beat = StoryBeat(
                name=beat_data.get('name', f'Story Beat {idx + 1}'),
                sequence=self._safe_int(beat_data.get('sequence'), idx + 1),
                description=beat_data.get('description', ''),
                trigger=beat_data.get('trigger'),
                branches=beat_data.get('branches', []),
                related_locations=beat_data.get('related_locations', []),
                is_critical_path=beat_data.get('is_critical_path', False),
            )
            updates.story_beats.append(beat)

            # Create database record
            await self._create_story_beat_record(module, beat_data, idx)

        # Process connections
        connections = result.get('connections', [])
        self._log(f"Found {len(connections)} location connections")

        for conn_data in connections:
            conn = LocationConnection(
                from_location=str(conn_data.get('from_location', '')),
                to_location=str(conn_data.get('to_location', '')),
                connection_type=conn_data.get('connection_type', 'passage'),
                description=conn_data.get('description'),
                requirements=conn_data.get('requirements'),
            )
            updates.connections.append(conn)

        # Process location flow
        location_flow = result.get('location_flow', {})

        if location_flow.get('recommended_path'):
            updates.recommended_path = location_flow['recommended_path']
            self._log(f"Recommended path: {' -> '.join(updates.recommended_path[:5])}...")

        if result.get('critical_path'):
            updates.critical_path = result['critical_path']
            self._log(f"Critical path: {' -> '.join(updates.critical_path)}")

            # Update module with critical path if field exists
            if hasattr(module, 'critical_path'):
                module.critical_path = updates.critical_path
                await self.db.flush()

        # Update module with adventure flow if field exists
        if hasattr(module, 'adventure_flow') and context.adventure_flow:
            module.adventure_flow = context.adventure_flow
            await self.db.flush()

        await self.db.flush()

        self._log(f"Extracted {len(updates.story_beats)} story beats")
        self._log(f"Identified {len(updates.connections)} connections")

        return updates

    async def _create_story_beat_record(
        self,
        module: AdventureModule,
        beat_data: Dict[str, Any],
        default_sequence: int,
    ) -> AdventureStoryBeat:
        """Create AdventureStoryBeat database record."""
        beat = AdventureStoryBeat(
            module_id=module.id,
            name=beat_data.get('name', 'Story Beat'),
            sequence=self._safe_int(beat_data.get('sequence'), default_sequence),
            description=beat_data.get('description'),
            trigger=beat_data.get('trigger'),
            branches=beat_data.get('branches', []),
            related_locations=beat_data.get('related_locations', []),
            is_critical_path=beat_data.get('is_critical_path', False),
        )

        self.db.add(beat)
        return beat
