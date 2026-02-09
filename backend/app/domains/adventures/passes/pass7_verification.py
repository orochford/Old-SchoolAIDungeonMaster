"""Pass 7: Verification & Gap Filling.

This pass ensures completeness and fixes gaps:
- Compare expected vs actual extractions
- Identify specific gaps
- Re-extract missing pieces
- Final validation
"""

import logging
import re
from typing import Dict, Any, List, Set

from sqlalchemy import select, func

from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, AdventureItem, AdventureStoryBeat,
    EncounterType
)
from app.domains.adventures.extraction_context import ExtractionContext
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS7_GAP_FILL_PROMPT = """You are filling in gaps in an adventure module extraction.

## WHAT WE HAVE EXTRACTED
{context}

## MISSING ITEMS
The following items appear to be missing or incomplete:
{gaps}

## YOUR TASK
Extract the missing information from the text. Only extract what's listed as missing.

## OUTPUT FORMAT
Respond with a JSON object containing only the missing items:
```json
{{
  "locations": [/* only missing locations */],
  "encounters": [/* only missing encounters */],
  "npcs": [/* only missing NPCs */]
}}
```

## TEXT TO ANALYZE
{text}
"""


class VerificationPass(BasePass):
    """Pass 7: Verify extraction and fill gaps."""

    name = "pass7_verification"
    description = "Verify extraction and fill gaps"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Verify and fill gaps.

        Input: Preprocessor expected counts + full context
        Output: Gap-filled data, verification issues
        """
        self._log("Verifying extraction quality...")
        updates = ExtractionContext()

        # Gather current counts from database
        counts = await self._get_current_counts(module)

        # Compare against expected
        issues = self._compare_expected_vs_actual(preprocessed, counts, context)

        for issue in issues:
            self._log(f"Issue: {issue}")
            updates.verification_issues.append(issue)

        # Identify specific gaps
        gaps = await self._identify_gaps(module, preprocessed, context, full_text)

        if gaps['missing_locations'] or gaps['missing_encounters']:
            self._log(f"Found gaps: {len(gaps['missing_locations'])} locations, "
                     f"{len(gaps['missing_encounters'])} encounters")

            # Attempt to fill gaps
            await self._fill_gaps(module, full_text, context, gaps, updates)
        else:
            self._log("No significant gaps found")

        # Final statistics
        final_counts = await self._get_current_counts(module)
        self._log(f"Final counts: {final_counts['locations']} locations, "
                 f"{final_counts['encounters']} encounters, "
                 f"{final_counts['npcs']} NPCs, "
                 f"{final_counts['items']} items, "
                 f"{final_counts['story_beats']} story beats")

        return updates

    async def _get_current_counts(self, module: AdventureModule) -> Dict[str, int]:
        """Get current extraction counts from database."""
        locations = await self.db.execute(
            select(func.count(AdventureLocation.id))
            .where(AdventureLocation.module_id == module.id)
        )
        npcs = await self.db.execute(
            select(func.count(AdventureNPC.id))
            .where(AdventureNPC.module_id == module.id)
        )
        encounters = await self.db.execute(
            select(func.count(AdventureEncounter.id))
            .where(AdventureEncounter.module_id == module.id)
        )
        items = await self.db.execute(
            select(func.count(AdventureItem.id))
            .where(AdventureItem.module_id == module.id)
        )
        story_beats = await self.db.execute(
            select(func.count(AdventureStoryBeat.id))
            .where(AdventureStoryBeat.module_id == module.id)
        )

        return {
            'locations': locations.scalar() or 0,
            'encounters': encounters.scalar() or 0,
            'npcs': npcs.scalar() or 0,
            'items': items.scalar() or 0,
            'story_beats': story_beats.scalar() or 0,
        }

    def _compare_expected_vs_actual(
        self,
        preprocessed: Dict[str, Any],
        counts: Dict[str, int],
        context: ExtractionContext,
    ) -> List[str]:
        """Compare expected vs actual extractions."""
        issues = []

        # Expected from preprocessing
        expected_rooms = len(preprocessed.get('rooms', []))
        expected_wandering = sum(
            len(t.get('entries', []))
            for t in preprocessed.get('wandering_tables', [])
        )

        # Check locations
        if expected_rooms > 0:
            extraction_rate = counts['locations'] / expected_rooms
            if extraction_rate < 0.5:
                issues.append(
                    f"CRITICAL: Low location extraction rate: {counts['locations']}/{expected_rooms} "
                    f"({extraction_rate:.0%})"
                )
            elif extraction_rate < 0.8:
                issues.append(
                    f"WARNING: Some locations may be missing: {counts['locations']}/{expected_rooms} "
                    f"({extraction_rate:.0%})"
                )

        # Check encounters
        if counts['encounters'] == 0 and expected_wandering > 0:
            issues.append(
                f"WARNING: No encounters extracted, expected at least {expected_wandering} wandering"
            )

        # Check for suspiciously low counts
        if expected_rooms > 20 and counts['locations'] < 10:
            issues.append(
                f"WARNING: Preprocessor found {expected_rooms} rooms but only {counts['locations']} extracted"
            )

        # Check context consistency
        context_locations = len(context.locations)
        if context_locations != counts['locations']:
            issues.append(
                f"INFO: Context has {context_locations} locations but DB has {counts['locations']}"
            )

        return issues

    async def _identify_gaps(
        self,
        module: AdventureModule,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
        full_text: str,
    ) -> Dict[str, Any]:
        """Identify specific gaps in extraction."""
        gaps = {
            'missing_locations': [],
            'missing_encounters': [],
            'locations_without_encounters': [],
        }

        # Get extracted location keys
        result = await self.db.execute(
            select(AdventureLocation.location_key)
            .where(AdventureLocation.module_id == module.id)
        )
        extracted_keys = {row[0] for row in result.fetchall()}

        # Find missing locations from preprocessing
        for room in preprocessed.get('rooms', []):
            key = room.get('location_key', '')
            if key and key not in extracted_keys:
                gaps['missing_locations'].append({
                    'key': key,
                    'name': room.get('name', 'Unknown'),
                    'text': room.get('full_text', room.get('start_text', ''))[:500],
                })

        # Check for dangling exits directly from DB location exit data
        # This works during initial parsing (before graph is built)
        already_listed = {g['key'] for g in gaps['missing_locations']}
        try:
            result = await self.db.execute(
                select(AdventureLocation)
                .where(AdventureLocation.module_id == module.id)
            )
            all_locations = list(result.scalars().all())

            for loc in all_locations:
                if not loc.exits or not isinstance(loc.exits, dict):
                    continue
                for direction, dest_value in loc.exits.items():
                    # Extract the room key from exit values like "2", "Area 2", "Room 2 (locked)"
                    dest_key = self._extract_exit_key(str(dest_value))
                    if dest_key and dest_key not in extracted_keys and dest_key not in already_listed:
                        gaps['missing_locations'].append({
                            'key': dest_key,
                            'name': f'Location {dest_key} (referenced from exit)',
                            'text': f'Exit from {loc.location_key} ({loc.name}) direction {direction}',
                        })
                        already_listed.add(dest_key)
                        self._log(f"  Dangling exit: {loc.location_key} -> {direction} -> {dest_key}")
        except Exception as e:
            self._log(f"  Warning: Could not check exits for dangling references: {e}")

        # Find locations that should have encounters but don't
        locations_with_encounters = set()
        result = await self.db.execute(
            select(AdventureEncounter.location_id)
            .where(AdventureEncounter.module_id == module.id)
            .where(AdventureEncounter.location_id.isnot(None))
        )
        for row in result.fetchall():
            locations_with_encounters.add(row[0])

        # Check if source text mentions monsters in locations without encounters
        for key in extracted_keys:
            if key not in context.encounters or not context.encounters[key]:
                # Check source text for monster mentions
                if self._location_likely_has_monsters(key, full_text):
                    gaps['missing_encounters'].append({
                        'location_key': key,
                        'reason': 'Source text mentions monsters',
                    })

        return gaps

    def _extract_exit_key(self, exit_value: str) -> str:
        """Extract a room key from an exit destination string.

        Handles formats like: "2", "Area 2", "Room 2", "2 (locked door)",
        "east_corridor", etc.
        """
        if not exit_value:
            return ""
        exit_value = exit_value.strip()

        # Try to extract a bare number first (most common: "2", "14a")
        num_match = re.match(r'^(\d+[a-z]?)(?:\s|$|\()', exit_value)
        if num_match:
            return num_match.group(1)

        # Try "Room X" or "Area X" patterns
        area_match = re.match(r'(?:room|area|location)\s+(\d+[a-z]?)', exit_value, re.IGNORECASE)
        if area_match:
            return area_match.group(1)

        # For non-numeric keys (like "east_corridor"), return as-is if it looks like a key
        if re.match(r'^[a-z_]+$', exit_value, re.IGNORECASE):
            return exit_value

        return ""

    def _location_likely_has_monsters(self, location_key: str, full_text: str) -> bool:
        """Check if source text suggests location has monsters."""
        # Find the location section
        pattern = rf'\b{re.escape(location_key)}\.\s+[A-Z]'
        match = re.search(pattern, full_text)
        if not match:
            return False

        # Get surrounding text
        start = match.start()
        end = min(start + 2000, len(full_text))
        section = full_text[start:end].lower()

        # Look for monster indicators
        monster_indicators = [
            'monster:', 'monsters:', 'creature:', 'creatures:',
            'guard', 'patrol', 'lair', 'nest',
            'ac ', 'hd ', 'hp ', 'thac0',
            'attack', 'damage', 'morale',
        ]

        for indicator in monster_indicators:
            if indicator in section[:500]:  # Only check first 500 chars of room
                return True

        return False

    def _extract_targeted_sections(self, full_text: str, missing_keys: List[str]) -> str:
        """Extract targeted text sections around each missing room key.

        Instead of sending the entire document (which gets truncated and causes
        the LLM to miss rooms deep in the text), we find the specific section
        for each missing room and send only those sections.

        Prefers ALL CAPS room descriptions over wandering monster table entries
        that share the same numbering pattern.
        """
        sections = []

        for key in missing_keys:
            escaped = re.escape(key)
            pattern = rf'(?:^|\n)\s*\*?\*?{escaped}\.\s+([A-Z])'
            candidates = []
            for match in re.finditer(pattern, full_text):
                start = max(0, match.start() - 50)
                end = min(len(full_text), match.start() + 3000)
                section = full_text[start:end]
                after_num = full_text[match.start():match.start() + 200]
                name_match = re.search(rf'{escaped}\.\s+([A-Z][A-Z \'&]+)', after_num)
                is_room_desc = bool(name_match and len(name_match.group(1)) > 3)
                has_room_markers = 'Monster:' in section or 'Treasure' in section
                candidates.append((section, is_room_desc, has_room_markers, match.start()))

            if candidates:
                candidates.sort(key=lambda c: (c[1], c[2], c[3]), reverse=True)
                sections.append(f"--- Section for room {key} ---")
                sections.append(candidates[0][0])

        if sections:
            self._log(f"  Extracted {len(sections)//2} targeted text sections for missing rooms")
            return "\n\n".join(sections)
        return full_text

    async def _fill_gaps(
        self,
        module: AdventureModule,
        full_text: str,
        context: ExtractionContext,
        gaps: Dict[str, Any],
        updates: ExtractionContext,
    ) -> None:
        """Attempt to fill identified gaps using batched LLM calls with per-room retry."""
        if not gaps['missing_locations'] and not gaps['missing_encounters']:
            return

        missing_locs = gaps['missing_locations']  # No cap - process ALL missing
        self._log(f"Attempting to fill {len(missing_locs)} missing locations")

        context_prompt = context.to_context_prompt(['overview', 'locations_summary'])
        batch_size = 5

        # Process missing locations in batches of 5
        for batch_start in range(0, len(missing_locs), batch_size):
            batch = missing_locs[batch_start:batch_start + batch_size]
            batch_num = (batch_start // batch_size) + 1
            total_batches = (len(missing_locs) + batch_size - 1) // batch_size

            self._log(f"  Gap-fill batch {batch_num}/{total_batches} ({len(batch)} rooms)")

            # Build gap description for this batch
            gap_text = "## MISSING LOCATIONS\n"
            for loc in batch:
                gap_text += f"- {loc['key']}. {loc['name']}: {loc['text'][:100]}...\n"

            gap_text += "\n## LOCATIONS POSSIBLY MISSING ENCOUNTERS\n"
            for enc in gaps['missing_encounters'][:10]:
                gap_text += f"- Location {enc['location_key']}: {enc['reason']}\n"

            # Extract targeted text for this batch's rooms
            batch_keys = [loc['key'] for loc in batch]
            targeted_text = self._extract_targeted_sections(full_text, batch_keys)

            prompt = PASS7_GAP_FILL_PROMPT.replace("{context}", context_prompt)
            prompt = prompt.replace("{gaps}", gap_text)

            result = await self._call_llm(prompt, targeted_text, stage_name=f"pass7_gap_fill_batch_{batch_num}")

            if not result:
                self._log(f"  WARNING: No data for gap-fill batch {batch_num}")
                # Retry each room individually since entire batch failed
                for loc_info in batch:
                    await self._fill_single_location(module, full_text, context_prompt, loc_info, gaps, updates)
                continue

            # Process filled locations from this batch
            filled_locations = result.get('locations', [])
            filled_keys = set()
            for loc_data in filled_locations:
                location_key = str(loc_data.get('location_key', ''))
                if not location_key:
                    continue
                filled_keys.add(location_key)

                exists = await self.db.execute(
                    select(AdventureLocation)
                    .where(AdventureLocation.module_id == module.id)
                    .where(AdventureLocation.location_key == location_key)
                )
                if exists.scalar_one_or_none():
                    continue

                location = AdventureLocation(
                    module_id=module.id,
                    location_key=location_key,
                    name=loc_data.get('name', f'Location {location_key}'),
                    dm_description=loc_data.get('dm_description', 'Gap-filled location'),
                    read_aloud_text=loc_data.get('read_aloud_text'),
                    features=loc_data.get('features', []),
                    exits=loc_data.get('exits', {}) if isinstance(loc_data.get('exits'), dict) else {},
                    traps=loc_data.get('traps', []),
                    secrets=loc_data.get('secrets', []),
                    treasure=loc_data.get('treasure', []),
                    dungeon_level=self._safe_int(loc_data.get('dungeon_level'), 1),
                )
                self.db.add(location)
                updates.gaps_filled.append(f"Location {location_key}")
                self._log(f"    Gap-filled location {location_key}")

            # Retry individually for rooms missing from this batch's response
            expected_keys = set(batch_keys)
            missing_from_batch = expected_keys - filled_keys
            if missing_from_batch:
                self._log(f"    Batch {batch_num}: {len(missing_from_batch)} room(s) missing from response, retrying individually")
                for missing_key in missing_from_batch:
                    loc_info = next((loc for loc in batch if loc['key'] == missing_key), None)
                    if loc_info:
                        await self._fill_single_location(module, full_text, context_prompt, loc_info, gaps, updates)

            # Process filled encounters (only on first batch to avoid duplicates)
            if batch_start == 0:
                filled_encounters = result.get('encounters', [])
                for enc_data in filled_encounters:
                    location_key = enc_data.get('location_key')
                    if not location_key:
                        continue

                    loc_result = await self.db.execute(
                        select(AdventureLocation)
                        .where(AdventureLocation.module_id == module.id)
                        .where(AdventureLocation.location_key == str(location_key))
                    )
                    location = loc_result.scalar_one_or_none()

                    encounter = AdventureEncounter(
                        module_id=module.id,
                        location_id=location.id if location else None,
                        encounter_type=EncounterType.FIXED,
                        name=enc_data.get('name', 'Gap-filled Encounter'),
                        description=enc_data.get('description'),
                        creatures=enc_data.get('creatures', []),
                        tactics=enc_data.get('tactics'),
                        treasure=enc_data.get('treasure', []),
                        xp_value=self._safe_int(enc_data.get('xp_value')),
                    )
                    self.db.add(encounter)
                    updates.gaps_filled.append(f"Encounter in {location_key}")
                    self._log(f"    Gap-filled encounter in {location_key}")

            await self.db.flush()

        # Re-check: report any rooms still missing after all gap-fill attempts
        result = await self.db.execute(
            select(AdventureLocation.location_key)
            .where(AdventureLocation.module_id == module.id)
        )
        final_extracted_keys = {row[0] for row in result.fetchall()}
        still_missing = [loc['key'] for loc in missing_locs if loc['key'] not in final_extracted_keys]
        if still_missing:
            self._log(f"  WARNING: {len(still_missing)} rooms still missing after gap-fill: {sorted(still_missing)}")
            updates.verification_issues.append(
                f"Gap-fill incomplete: {len(still_missing)} rooms still missing: {sorted(still_missing)}"
            )

        self._log(f"Filled {len(updates.gaps_filled)} gaps")

    async def _fill_single_location(
        self,
        module: AdventureModule,
        full_text: str,
        context_prompt: str,
        loc_info: Dict[str, Any],
        gaps: Dict[str, Any],
        updates: ExtractionContext,
    ) -> None:
        """Retry gap-fill for a single missing location."""
        key = loc_info['key']

        # Check if already exists (may have been created by another path)
        exists = await self.db.execute(
            select(AdventureLocation)
            .where(AdventureLocation.module_id == module.id)
            .where(AdventureLocation.location_key == key)
        )
        if exists.scalar_one_or_none():
            return

        gap_text = f"## MISSING LOCATIONS\n- {key}. {loc_info['name']}: {loc_info['text'][:200]}...\n"
        targeted_text = self._extract_targeted_sections(full_text, [key])

        prompt = PASS7_GAP_FILL_PROMPT.replace("{context}", context_prompt)
        prompt = prompt.replace("{gaps}", gap_text)

        result = await self._call_llm(prompt, targeted_text, stage_name=f"pass7_retry_{key}")
        if not result:
            self._log(f"      Retry failed for room {key}")
            return

        for loc_data in result.get('locations', []):
            location_key = str(loc_data.get('location_key', ''))
            if location_key != key:
                continue

            location = AdventureLocation(
                module_id=module.id,
                location_key=location_key,
                name=loc_data.get('name', f'Location {location_key}'),
                dm_description=loc_data.get('dm_description', 'Gap-filled location'),
                read_aloud_text=loc_data.get('read_aloud_text'),
                features=loc_data.get('features', []),
                exits=loc_data.get('exits', {}) if isinstance(loc_data.get('exits'), dict) else {},
                traps=loc_data.get('traps', []),
                secrets=loc_data.get('secrets', []),
                treasure=loc_data.get('treasure', []),
                dungeon_level=self._safe_int(loc_data.get('dungeon_level'), 1),
            )
            self.db.add(location)
            updates.gaps_filled.append(f"Location {location_key}")
            self._log(f"      Retry success: gap-filled location {location_key}")
            await self.db.flush()
            break
