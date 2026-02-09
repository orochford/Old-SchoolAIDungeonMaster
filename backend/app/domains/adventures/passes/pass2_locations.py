"""Pass 2: Location details extraction (batched, per-location).

This pass extracts full location details with awareness of overall adventure:
- Full location details (features, exits, dimensions)
- DM description vs read-aloud separation
- Visible vs hidden elements
- Treasure not guarded by monsters
"""

import logging
import re
from typing import Dict, Any, List
from uuid import UUID

from sqlalchemy import select

from app.domains.adventures.models import AdventureModule, AdventureLocation
from app.domains.adventures.extraction_context import (
    ExtractionContext, LocationDetails
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


# Common patterns that indicate AI-generated content rather than verbatim extraction
AI_GENERATION_PATTERNS = [
    "allowing for",
    "positioned defensively",
    "speaks to",
    "provides a",
    "the air feels",
    "you notice",
    "suggests that",
    "appears to be",
    "seems to have",
    "likely used for",
    "would have been",
    "creating an atmosphere",
]


PASS2_LOCATION_PROMPT = """You are extracting detailed information about locations from a tabletop RPG adventure module.

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Extract detailed information for the following location(s). For each location:

1. **dm_description**: QUOTE THE EXACT TEXT from the module for this location.
   Copy word-for-word - do NOT paraphrase, summarize, or add commentary.
   If the module says "empty and barren" write exactly "empty and barren".
   Include ALL text for this location, including special features like magic mouths.
2. **read_aloud_text**: QUOTE VERBATIM any boxed or italicized read-aloud text.
   Copy exactly as written - do not paraphrase or "improve" the text.
3. **features**: Notable features as list of {{"name": "...", "details": "..."}}
4. **exits**: Exits mapping direction to destination (e.g., {{"north": "2", "secret_east": "7"}})
5. **visible_items**: Items/features immediately visible to players
6. **hidden_elements**: Hidden things with {{"type": "...", "location": "...", "detection": "..."}}
7. **treasure**: Unguarded treasure with {{"item": "...", "value": "...", "location": "..."}}
8. **traps**: ALL traps including:
   - Physical traps (pit traps, arrow traps, portcullises)
   - Magical traps (magic mouth spells, glyphs, wards, illusions)
   - Environmental hazards (collapsing ceilings, gas)
   Format: {{"name": "...", "trigger": "...", "effect": "...", "detection": "...", "disarm": "...", "is_magical": true/false}}
9. **secrets**: ALL secret/hidden features including:
   - Secret doors (one-way or two-way)
   - Hidden passages
   - Concealed compartments
   Format: {{"type": "...", "detection": "...", "description": "...", "destination": "..."}}
10. **dungeon_level**: Level number (1, 2, etc.)
11. **tier**: Region name if mentioned (e.g., "Upper Caves")

## CRITICAL - EXTRACT ALL SPECIAL FEATURES
Pay special attention to:
- **Magic Mouth** spells - include the EXACT dialogue/message spoken
- **One-way doors** - note which side can detect/use them
- **Teleporters** - note destinations and triggers
- **Illusions** - what they conceal and how to detect
- **Portcullises and gates** - triggers and mechanisms
- **Wind corridors** - effects on light sources

## IMPORTANT
- Separate DM-only information from player-safe descriptions
- Note what players see immediately vs what requires searching
- Include ALL exits including secret ones
- For magical effects, include the FULL TEXT of any spoken messages or inscriptions

## CRITICAL: EXIT DIRECTIONS
- Only include exits that are EXPLICITLY described in THIS room's text
- Use the EXACT direction stated in the module (north, south, east, west, etc.)
- If the module says "a passage leads north to room 2", record {{"north": "2"}}
- Do NOT invent directions or infer them from other rooms
- If a room text doesn't explicitly state a direction, DO NOT include that exit
- Example: If room 2's text says "south leads back to room 1" then room 2 has {{"south": "1"}}
- Do NOT assume that if room 1 goes north to room 2, then room 2 goes south to room 1

## OUTPUT FORMAT
```json
{{
  "locations": [
    {{
      "location_key": "1",
      "name": "Entrance Alcoves",
      "dm_description": "[Copy exact text from module here - e.g. 'These guardpoints are all empty and barren of any markings.']",
      "read_aloud_text": "[Copy exact boxed/italicized text - e.g. 'The passage is cold and damp.']",
      "features": [{{"name": "Alcoves", "details": "Three pairs of alcoves line the corridor..."}}],
      "exits": {{"north": "2", "secret_east": "7"}},
      "visible_items": ["Stone alcoves", "Arrow slits"],
      "hidden_elements": [{{"type": "one-way_door", "location": "second pair of alcoves", "detection": "undetectable from entrance side"}}],
      "treasure": [],
      "traps": [
        {{
          "name": "Magic Mouth",
          "trigger": "passing between the third pair of alcoves",
          "effect": "Two mouths appear and speak: East mouth: 'WHO DARES ENTER THIS PLACE AND INTRUDE UPON THE SANCTUARY OF ITS INHABITANTS?' West mouth: 'ONLY A GROUP OF FOOLHARDY EXPLORERS DOOMED TO CERTAIN DEATH!' Both: 'WOE TO ANY WHO PASS THIS PLACE—THE WRATH OF ZELLIGAR AND ROGAHN WILL BE UPON THEM!' followed by raucous laughter",
          "detection": "Detect Magic reveals magical aura",
          "disarm": "Cannot be disarmed - permanent feature",
          "is_magical": true
        }}
      ],
      "secrets": [
        {{
          "type": "one-way_secret_door",
          "detection": "undetectable from entrance corridor, visible from other side",
          "description": "Second pair of alcoves contain secret one-way doors for guards to appear behind invaders",
          "destination": "guard stations"
        }}
      ],
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

    def _validate_extraction(self, location_data: dict, source_text: str) -> None:
        """Warn if extracted descriptions appear AI-generated rather than verbatim.

        Checks for common AI-generation patterns that wouldn't appear in
        the original module text.
        """
        dm_desc = location_data.get('dm_description', '').lower()
        location_name = location_data.get('name', 'Unknown')
        source_lower = source_text.lower()

        for pattern in AI_GENERATION_PATTERNS:
            if pattern in dm_desc and pattern not in source_lower:
                logger.warning(
                    f"Possible AI-generated content in '{location_name}': "
                    f"found '{pattern}' in description but not in source text"
                )

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

                # Find source text for this room and validate extraction
                room_source_text = ""
                for room in batch:
                    if str(room.get('location_key', '')) == location_key:
                        room_source_text = self._extract_location_text(full_text, room)
                        break
                if room_source_text:
                    self._validate_extraction(loc_data, room_source_text)

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
                    module, loc_data, batch, location_ids, room_source_text
                )
                if db_location:
                    location_ids[location_key] = db_location.id
                    self._log(f"  [{len(updates.locations)}/{total}] {loc_details.name}")

            await self.db.flush()

            # Per-batch verification: retry individually for any rooms the LLM missed
            extracted_keys_in_batch = {str(loc.get('location_key', '')) for loc in extracted_locs}
            expected_keys_in_batch = {str(r.get('location_key', '')) for r in batch}
            missing_from_batch = expected_keys_in_batch - extracted_keys_in_batch

            if missing_from_batch:
                self._log(f"  Batch {batch_num}: {len(missing_from_batch)} room(s) missing, retrying individually: {missing_from_batch}")
                for missing_key in missing_from_batch:
                    missing_room = next((r for r in batch if str(r.get('location_key', '')) == missing_key), None)
                    if not missing_room:
                        continue

                    single_text = self._build_batch_text(full_text, [missing_room], rooms)
                    retry_prompt = PASS2_LOCATION_PROMPT.replace("{context}", context_prompt)
                    retry_result = await self._call_llm(
                        retry_prompt, single_text,
                        stage_name=f"pass2_retry_{missing_key}"
                    )

                    if not retry_result:
                        self._log(f"    Retry failed for room {missing_key}")
                        continue

                    retry_locs = retry_result.get('locations', [])
                    for loc_data in retry_locs:
                        location_key = str(loc_data.get('location_key', ''))
                        if not location_key or location_key in updates.locations:
                            continue

                        room_source_text = self._extract_location_text(full_text, missing_room)
                        if room_source_text:
                            self._validate_extraction(loc_data, room_source_text)

                        exits = loc_data.get('exits', {})
                        if not isinstance(exits, dict):
                            exits = {}

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

                        db_location = await self._create_location_record(
                            module, loc_data, batch, location_ids, room_source_text
                        )
                        if db_location:
                            location_ids[location_key] = db_location.id
                            self._log(f"    Retry success: [{len(updates.locations)}/{total}] {loc_details.name}")

                    await self.db.flush()

        self._log(f"Extracted {len(updates.locations)} locations")

        # Post-process: Detect template-only rooms (e.g. B1's blank "Monster: / Treasure:" rooms)
        # and give them a proper placeholder instead of raw template text
        TEMPLATE_PATTERNS = ['monster:', 'treasure & location:', 'treasure:']
        for loc_key, loc in updates.locations.items():
            desc = (loc.dm_description or '').strip()
            # Check if description is ONLY template headers with no real content
            desc_lower = desc.lower()
            stripped = desc_lower
            for pat in TEMPLATE_PATTERNS:
                stripped = stripped.replace(pat, '')
            # Also remove "adjacent locations" lines the LLM adds
            stripped = re.sub(r'adjacent locations.*', '', stripped, flags=re.DOTALL)
            stripped = stripped.strip()
            if not stripped and desc_lower:
                # This is a template-only room — replace with meaningful placeholder
                loc.dm_description = (
                    f"This {loc.name.lower()} is left intentionally unstocked. "
                    "The DM should populate it with monsters, treasure, and details as desired."
                )
                result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module.id)
                    .where(AdventureLocation.location_key == loc_key)
                )
                db_loc = result.scalar_one_or_none()
                if db_loc:
                    db_loc.dm_description = loc.dm_description
                    db_loc.source_text = 'Blank room - DM to stock with monsters and treasure.'
                self._log(f"  Template-only room detected: {loc_key}. {loc.name}")

        await self.db.flush()

        # Post-process: Re-extract locations with empty descriptions
        empty_locs = [
            (key, loc) for key, loc in updates.locations.items()
            if not loc.dm_description or loc.dm_description.strip() in ('', 'No description available.', 'Gap-filled location')
        ]

        if empty_locs:
            self._log(f"  {len(empty_locs)} location(s) have empty descriptions, re-extracting...")
            for loc_key, loc in empty_locs:
                room = next((r for r in rooms if str(r.get('location_key', '')) == loc_key), None)
                if not room:
                    continue
                single_text = self._build_batch_text(full_text, [room], rooms)
                retry_prompt = PASS2_LOCATION_PROMPT.replace("{context}", context_prompt)
                retry_result = await self._call_llm(retry_prompt, single_text, stage_name=f"pass2_enrich_{loc_key}")
                if not retry_result:
                    continue
                retry_locs = retry_result.get('locations', [])
                for loc_data in retry_locs:
                    if str(loc_data.get('location_key', '')) == loc_key and loc_data.get('dm_description'):
                        # Update context record — description enrichment only
                        # Do NOT overwrite exits/traps/secrets if they already have data
                        loc.dm_description = loc_data['dm_description']
                        loc.read_aloud_text = loc_data.get('read_aloud_text') or loc.read_aloud_text
                        if not loc.features and loc_data.get('features'):
                            loc.features = loc_data['features']
                        if not loc.visible_items and loc_data.get('visible_items'):
                            loc.visible_items = loc_data['visible_items']
                        if not loc.hidden_elements and loc_data.get('hidden_elements'):
                            loc.hidden_elements = loc_data['hidden_elements']
                        # Only adopt exits if we currently have none
                        new_exits = loc_data.get('exits')
                        if not loc.exits and isinstance(new_exits, dict) and new_exits:
                            loc.exits = new_exits
                        if not loc.treasure and loc_data.get('treasure'):
                            loc.treasure = loc_data['treasure']
                        if not loc.traps and loc_data.get('traps'):
                            loc.traps = loc_data['traps']
                        if not loc.secrets and loc_data.get('secrets'):
                            loc.secrets = loc_data['secrets']

                        # Update DB record
                        result = await self.db.execute(
                            select(AdventureLocation)
                            .where(AdventureLocation.module_id == module.id)
                            .where(AdventureLocation.location_key == loc_key)
                        )
                        db_loc = result.scalar_one_or_none()
                        if db_loc:
                            db_loc.dm_description = loc.dm_description
                            db_loc.read_aloud_text = loc.read_aloud_text
                            if loc.features:
                                db_loc.features = loc.features
                            if loc.exits:
                                db_loc.exits = loc.exits
                            if loc.traps:
                                db_loc.traps = loc.traps
                            if loc.secrets:
                                db_loc.secrets = loc.secrets
                            if loc.treasure:
                                db_loc.treasure = loc.treasure

                        self._log(f"    Re-extracted description for {loc_key}: {loc.name}")
                        break

            await self.db.flush()

        # Post-process: Reconcile exit directions
        await self._reconcile_exits(module.id, updates)

        return updates

    async def _reconcile_exits(
        self,
        module_id: UUID,
        context: ExtractionContext
    ) -> None:
        """Post-process to fix inconsistent exit directions.

        If room A says north→B, then room B should say south→A (opposite direction).
        This fixes cases where the LLM extracted incorrect directions.
        """
        self._log("Reconciling exit directions...")

        opposite_dirs = {
            'north': 'south', 'south': 'north',
            'east': 'west', 'west': 'east',
            'northeast': 'southwest', 'southwest': 'northeast',
            'northwest': 'southeast', 'southeast': 'northwest',
            'up': 'down', 'down': 'up',
        }

        fixes_made = 0
        warnings = []

        # Build a map of all exits
        all_exits: Dict[str, Dict[str, str]] = {}  # location_key -> {direction: destination}
        for loc_key, loc in context.locations.items():
            all_exits[loc_key] = dict(loc.exits) if loc.exits else {}

        # Check for inconsistencies
        for loc_key, exits in all_exits.items():
            for direction, dest_key in exits.items():
                # Skip secret exits - they may intentionally be one-way
                if 'secret' in direction.lower():
                    continue

                # Get the base direction (remove prefixes like "secret_")
                base_dir = direction.lower().replace('_door', '').replace('secret_', '')
                opposite = opposite_dirs.get(base_dir)

                if not opposite:
                    continue

                # Check if destination has a return path
                dest_exits = all_exits.get(dest_key, {})
                return_dest = None

                # Look for any exit from dest back to this location
                for dest_dir, dest_dest in dest_exits.items():
                    if dest_dest == loc_key:
                        return_dest = dest_dir
                        break

                if return_dest is None:
                    # Destination has no return path - add one
                    warnings.append(
                        f"  {loc_key}→{direction}→{dest_key} but {dest_key} has no return to {loc_key}"
                    )
                    # Add the missing return exit
                    if dest_key in context.locations:
                        if context.locations[dest_key].exits is None:
                            context.locations[dest_key].exits = {}
                        context.locations[dest_key].exits[opposite] = loc_key
                        all_exits[dest_key][opposite] = loc_key
                        fixes_made += 1

                elif return_dest.lower().replace('_door', '').replace('secret_', '') != opposite:
                    # Return path exists but direction is wrong
                    warnings.append(
                        f"  {loc_key}→{direction}→{dest_key} but {dest_key}→{return_dest}→{loc_key} "
                        f"(expected {dest_key}→{opposite}→{loc_key})"
                    )
                    # Fix the direction
                    if dest_key in context.locations:
                        old_exits = dict(context.locations[dest_key].exits or {})
                        # Remove wrong direction, add correct one
                        if return_dest in old_exits:
                            del old_exits[return_dest]
                        old_exits[opposite] = loc_key
                        context.locations[dest_key].exits = old_exits
                        all_exits[dest_key] = old_exits
                        fixes_made += 1

        # Update database records with fixed exits
        if fixes_made > 0:
            self._log(f"Found {len(warnings)} exit inconsistencies, fixed {fixes_made}")
            for warning in warnings[:10]:  # Log first 10
                self._log(warning)
            if len(warnings) > 10:
                self._log(f"  ... and {len(warnings) - 10} more")

            # Update DB records
            for loc_key, loc in context.locations.items():
                result = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module_id)
                    .where(AdventureLocation.location_key == loc_key)
                )
                db_loc = result.scalar_one_or_none()
                if db_loc and loc.exits:
                    db_loc.exits = loc.exits

            await self.db.flush()
            self._log("Exit reconciliation complete")

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
            return room['full_text'][:8000]  # Increased to capture more detail

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

        # Extract ~8000 characters starting from position to capture full descriptions
        # including traps, secrets, and magical effects that may follow the main text
        return full_text[start_pos:start_pos + 8000]

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
        source_text: str = "",
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
            source_text=source_text,  # Verbatim text from module
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
