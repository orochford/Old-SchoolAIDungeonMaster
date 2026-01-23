"""Pass 2: Location details extraction (batched, per-location).

This pass extracts full location details with awareness of overall adventure:
- Full location details (features, exits, dimensions)
- DM description vs read-aloud separation
- Visible vs hidden elements
- Treasure not guarded by monsters
"""

import logging
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy import select

from app.domains.adventures.models import AdventureModule, AdventureLocation
from app.domains.adventures.extraction_context import (
    ExtractionContext, LocationDetails
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS2_LOCATION_PROMPT = """You are extracting detailed information about locations from a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Extract detailed information for the following location(s). For each location:

1. **dm_description**: Complete DM description (everything the DM needs to know)
2. **read_aloud_text**: Text meant to be read aloud to players (boxed/italicized text)
3. **features**: Notable features as list of {{"name": "...", "details": "..."}}
4. **exits**: Exits mapping direction to destination (e.g., {{"north": "2", "secret_east": "7"}})
5. **visible_items**: Items/features immediately visible to players
6. **hidden_elements**: Hidden things with {{"type": "...", "location": "...", "detection": "..."}}
7. **treasure**: Unguarded treasure with {{"item": "...", "value": "...", "location": "..."}}
8. **traps**: Traps with {{"trigger": "...", "effect": "...", "detection": "...", "disarm": "..."}}
9. **secrets**: Secret doors/passages with {{"type": "...", "detection": "...", "description": "..."}}
10. **dungeon_level**: Level number (1, 2, etc.)
11. **tier**: Region name if mentioned (e.g., "Upper Caves")

## IMPORTANT
- Separate DM-only information from player-safe descriptions
- Note what players see immediately vs what requires searching
- Include ALL exits including secret ones

## OUTPUT FORMAT
```json
{{
  "locations": [
    {{
      "location_key": "5",
      "name": "Wizard's Chamber",
      "dm_description": "Full text for DM...",
      "read_aloud_text": "Player-safe description...",
      "features": [{{"name": "Bed", "details": "Simple wooden frame..."}}],
      "exits": {{"north": "6", "south": "4", "secret_east": "7"}},
      "visible_items": ["Desk", "Bookshelf"],
      "hidden_elements": [{{"type": "secret_door", "location": "east wall", "detection": "Search DC 15"}}],
      "treasure": [{{"item": "Silver candlestick", "value": "25gp", "location": "on desk"}}],
      "traps": [],
      "secrets": [{{"type": "secret_door", "detection": "1-in-6", "description": "leads to room 7"}}],
      "dungeon_level": 1,
      "tier": "Upper Level"
    }}
  ]
}}
```

## LOCATION TEXT TO ANALYZE
{text}
"""


class LocationsPass(BasePass):
    """Pass 2: Extract detailed location information."""

    name = "pass2_locations"
    description = "Extract full location details"

    def __init__(self, db):
        super().__init__(db)
        self.batch_size = 5

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Extract location details in batches.

        Input: Overview context + preprocessed room text
        Output: Full location details
        """
        self._log("Extracting location details...")
        updates = ExtractionContext()

        # Get rooms to process - prefer preprocessed, fall back to context
        rooms = preprocessed.get('rooms', [])
        if not rooms and context.location_list:
            self._log("No preprocessed rooms, using location list from Pass 1")
            rooms = [
                {
                    'location_key': loc.key,
                    'name': loc.name,
                    'start_text': loc.brief_desc,
                    'dungeon_level': loc.dungeon_level,
                }
                for loc in context.location_list
            ]

        if not rooms:
            self._log("WARNING: No rooms to process")
            return updates

        total = len(rooms)
        self._log(f"Processing {total} locations in batches of {self.batch_size}")

        # Build context prompt from Pass 1
        context_prompt = context.to_context_prompt(['overview', 'locations_brief'])

        # Track created location IDs for parent relationships
        location_ids: Dict[str, UUID] = {}

        # Process in batches
        for i in range(0, total, self.batch_size):
            batch = rooms[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (total + self.batch_size - 1) // self.batch_size

            self._log(f"Processing batch {batch_num}/{total_batches} ({len(batch)} locations)")

            # Build text for this batch
            batch_text = self._build_batch_text(full_text, batch, rooms)

            # Build prompt with context
            prompt = PASS2_LOCATION_PROMPT.replace("{context}", context_prompt)

            # Call LLM
            result = await self._call_llm(
                prompt,
                batch_text,
                stage_name=f"pass2_batch_{batch_num}"
            )

            if not result:
                self._log(f"WARNING: No data for batch {batch_num}")
                continue

            # Process extracted locations
            extracted_locs = result.get('locations', [])
            for loc_data in extracted_locs:
                location_key = str(loc_data.get('location_key', ''))
                if not location_key:
                    continue

                # Validate exits is a dict (LLM sometimes returns strings)
                exits = loc_data.get('exits', {})
                if not isinstance(exits, dict):
                    exits = {}

                # Create LocationDetails for context
                loc_details = LocationDetails(
                    location_key=location_key,
                    name=loc_data.get('name', 'Unknown'),
                    dm_description=loc_data.get('dm_description', ''),
                    read_aloud_text=loc_data.get('read_aloud_text'),
                    features=loc_data.get('features', []),
                    exits=exits,
                    visible_items=loc_data.get('visible_items', []),
                    hidden_elements=loc_data.get('hidden_elements', []),
                    treasure=loc_data.get('treasure', []),
                    traps=loc_data.get('traps', []),
                    secrets=loc_data.get('secrets', []),
                    dungeon_level=self._safe_int(loc_data.get('dungeon_level'), 1),
                    tier=loc_data.get('tier'),
                )
                updates.locations[location_key] = loc_details

                # Create database record
                db_location = await self._create_location_record(
                    module, loc_data, batch, location_ids
                )
                if db_location:
                    location_ids[location_key] = db_location.id
                    self._log(f"  [{len(updates.locations)}/{total}] {loc_details.name}")

            await self.db.flush()

        self._log(f"Extracted {len(updates.locations)} locations")
        return updates

    def _build_batch_text(
        self,
        full_text: str,
        batch: List[Dict[str, Any]],
        all_rooms: List[Dict[str, Any]]
    ) -> str:
        """Build text for a batch of locations."""
        parts = []

        for room in batch:
            location_key = room.get('location_key', '')
            location_name = room.get('name', 'Unknown')

            # Find the room text
            room_text = self._extract_location_text(full_text, room)

            parts.append(f"\n--- LOCATION {location_key}: {location_name} ---\n")
            parts.append(room_text)

            # Add adjacent room context
            adjacent = self._get_adjacent_rooms(room, all_rooms)
            if adjacent:
                parts.append("\nAdjacent locations (for exit reference):")
                for adj in adjacent[:3]:
                    parts.append(f"  - {adj['location_key']}. {adj['name']}")

        return "\n".join(parts)

    def _extract_location_text(
        self,
        full_text: str,
        room: Dict[str, Any]
    ) -> str:
        """Extract text for a specific location."""
        # Use full_text if available from preprocessing
        if room.get('full_text'):
            return room['full_text'][:5000]

        # Otherwise find by start_text
        start_text = room.get('start_text', '')
        if not start_text:
            return ""

        start_pos = full_text.find(start_text)
        if start_pos == -1:
            # Try partial match
            if len(start_text) > 20:
                start_pos = full_text.find(start_text[:20])

        if start_pos == -1:
            return start_text  # Just return what we have

        # Extract ~5000 characters starting from position
        return full_text[start_pos:start_pos + 5000]

    def _get_adjacent_rooms(
        self,
        room: Dict[str, Any],
        all_rooms: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Get rooms adjacent to this one (by number proximity)."""
        try:
            room_num = int(room.get('location_key', '0'))
        except ValueError:
            return []

        adjacent = []
        for other in all_rooms:
            try:
                other_num = int(other.get('location_key', '0'))
                if abs(other_num - room_num) <= 2 and other_num != room_num:
                    adjacent.append(other)
            except ValueError:
                continue

        return adjacent[:5]

    async def _create_location_record(
        self,
        module: AdventureModule,
        loc_data: Dict[str, Any],
        batch: List[Dict[str, Any]],
        location_ids: Dict[str, UUID],
    ) -> AdventureLocation:
        """Create AdventureLocation database record."""
        location_key = str(loc_data.get('location_key', ''))

        # Find original room data for parent info
        parent_key = None
        dungeon_level = self._safe_int(loc_data.get('dungeon_level'), 1)

        for room in batch:
            if room.get('location_key') == location_key:
                parent_key = room.get('parent_key')
                if room.get('dungeon_level'):
                    dungeon_level = room['dungeon_level']
                break

        # Get parent ID if exists
        parent_id = None
        if parent_key and parent_key in location_ids:
            parent_id = location_ids[parent_key]

        # Build name with fallback
        loc_name = loc_data.get('name')
        if not loc_name:
            for room in batch:
                if room.get('location_key') == location_key:
                    loc_name = room.get('name', f"Location {location_key}")
                    break
        loc_name = loc_name or f"Location {location_key}"

        # Build description with fallback
        loc_desc = loc_data.get('dm_description')
        if not loc_desc:
            for room in batch:
                if room.get('location_key') == location_key:
                    loc_desc = room.get('start_text', 'No description available.')
                    break
        loc_desc = loc_desc or "No description available."

        # Validate exits is a dict
        exits = loc_data.get('exits') or {}
        if not isinstance(exits, dict):
            exits = {}

        location = AdventureLocation(
            module_id=module.id,
            location_key=location_key,
            name=loc_name,
            dm_description=loc_desc,
            read_aloud_text=loc_data.get('read_aloud_text'),
            features=loc_data.get('features') or [],
            exits=exits,
            traps=loc_data.get('traps') or [],
            secrets=loc_data.get('secrets') or [],
            treasure=loc_data.get('treasure') or [],
            dungeon_level=dungeon_level,
            tier=loc_data.get('tier'),
            parent_location_id=parent_id,
        )

        self.db.add(location)
        await self.db.flush()

        return location
