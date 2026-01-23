"""Pass 5: Player Experience extraction.

This pass refines player-facing content:
- Improved read-aloud text for atmosphere
- Sensory details (sight, sound, smell)
- Mood and tone for each area
- Information reveal pacing
"""

import logging
from typing import Dict, Any

from sqlalchemy import select

from app.domains.adventures.models import AdventureModule, AdventureLocation
from app.domains.adventures.extraction_context import (
    ExtractionContext, AtmosphereNote
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS5_PLAYER_PROMPT = """You are refining player-facing content for a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Create or improve the player experience elements:

### READ-ALOUD TEXT
For each location, create evocative text the DM can read to players:
- Should NOT reveal hidden information (traps, secret doors, treasure locations)
- SHOULD create atmosphere and set the scene
- Focus on what characters would immediately notice
- Keep it to 2-4 sentences

### ATMOSPHERE & SENSORY DETAILS
For each location, note:
- sight: What do they see?
- sound: What do they hear?
- smell: What do they smell?
- touch: Temperature, air quality, textures
- mood: Overall emotional tone

### AREA THEMES
For larger sections (levels, wings):
- What's the overall feeling?
- How does it differ from other areas?
- What makes it memorable?

## OUTPUT FORMAT
```json
{{
  "read_aloud": {{
    "1": "The passage opens into a series of alcoves carved into the stone walls. Dust motes drift in your torchlight, and the air smells of age and abandonment. Arrow slits in the far wall suggest this was once a defensive position.",
    "5": "This chamber reeks of decay..."
  }},
  "atmosphere": {{
    "1": {{
      "sight": "Carved alcoves, dust, ancient stonework",
      "sound": "Echoing footsteps, distant dripping",
      "smell": "Dust, age, faint mustiness",
      "touch": "Cool, dry air",
      "mood": "Abandoned but once grand"
    }}
  }},
  "area_themes": {{
    "upper_level": "Abandoned grandeur - signs of hasty departure, faded glory",
    "lower_level": "Natural caverns - wilder, more dangerous, less worked stone"
  }}
}}
```

## TEXT TO ANALYZE
{text}
"""


class PlayerContentPass(BasePass):
    """Pass 5: Refine player-facing content."""

    name = "pass5_player"
    description = "Refine player-facing content and atmosphere"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Refine player content.

        Input: Full context including DM guidance
        Output: Refined read-aloud text, atmosphere notes
        """
        self._log("Refining player-facing content...")
        updates = ExtractionContext()

        # Build context
        context_prompt = context.to_context_prompt([
            'overview', 'locations_summary', 'dm_notes'
        ])

        # Call LLM
        prompt = PASS5_PLAYER_PROMPT.replace("{context}", context_prompt)
        result = await self._call_llm(prompt, full_text, stage_name="pass5_player")

        if not result:
            self._log("WARNING: No player content extracted")
            return updates

        # Process read-aloud text
        read_aloud = result.get('read_aloud', {})
        self._log(f"Generated read-aloud for {len(read_aloud)} locations")

        for location_key, text in read_aloud.items():
            updates.read_aloud[str(location_key)] = text

            # Update database record
            await self._update_location_read_aloud(module, location_key, text)

        # Process atmosphere
        atmosphere = result.get('atmosphere', {})
        self._log(f"Generated atmosphere for {len(atmosphere)} locations")

        for location_key, atm_data in atmosphere.items():
            atm = AtmosphereNote(
                sight=atm_data.get('sight'),
                sound=atm_data.get('sound'),
                smell=atm_data.get('smell'),
                touch=atm_data.get('touch'),
                mood=atm_data.get('mood'),
            )
            updates.atmosphere[str(location_key)] = atm

            # Update database record
            await self._update_location_atmosphere(module, location_key, atm_data)

        # Process area themes (store in context for later use)
        area_themes = result.get('area_themes', {})
        if area_themes:
            self._log(f"Extracted {len(area_themes)} area themes")
            # Could be stored on module if we add a field for it

        await self.db.flush()

        self._log(f"Refined {len(updates.read_aloud)} read-aloud texts")
        self._log(f"Created {len(updates.atmosphere)} atmosphere notes")

        return updates

    async def _update_location_read_aloud(
        self,
        module: AdventureModule,
        location_key: str,
        text: str,
    ) -> None:
        """Update location with refined read-aloud text."""
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module.id)
            .where(AdventureLocation.location_key == str(location_key))
        )
        location = result.scalar_one_or_none()

        if location:
            # Only update if current read_aloud is empty or shorter
            if not location.read_aloud_text or len(text) > len(location.read_aloud_text):
                location.read_aloud_text = text

    async def _update_location_atmosphere(
        self,
        module: AdventureModule,
        location_key: str,
        atm_data: Dict[str, Any],
    ) -> None:
        """Update location with atmosphere data."""
        result = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module.id)
            .where(AdventureLocation.location_key == str(location_key))
        )
        location = result.scalar_one_or_none()

        if location:
            # Store in atmosphere field if it exists
            if hasattr(location, 'atmosphere'):
                # Build atmosphere string
                parts = []
                if atm_data.get('mood'):
                    parts.append(f"Mood: {atm_data['mood']}")
                if atm_data.get('sight'):
                    parts.append(f"Sight: {atm_data['sight']}")
                if atm_data.get('sound'):
                    parts.append(f"Sound: {atm_data['sound']}")
                if atm_data.get('smell'):
                    parts.append(f"Smell: {atm_data['smell']}")
                location.atmosphere = "\n".join(parts)

            # Store sensory details if field exists
            if hasattr(location, 'sensory_details'):
                location.sensory_details = {
                    'sight': atm_data.get('sight'),
                    'sound': atm_data.get('sound'),
                    'smell': atm_data.get('smell'),
                    'touch': atm_data.get('touch'),
                    'mood': atm_data.get('mood'),
                }
