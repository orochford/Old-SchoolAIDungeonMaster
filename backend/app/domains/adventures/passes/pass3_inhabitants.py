"""Pass 3: Inhabitants & Threats extraction.

This pass extracts all creatures with location context:
- Fixed encounters per location
- Wandering monster tables
- NPCs with motivations
"""

import logging
from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy import select

from app.domains.adventures.models import (
    AdventureModule, AdventureLocation, AdventureNPC,
    AdventureEncounter, EncounterType
)
from app.domains.adventures.extraction_context import (
    ExtractionContext, Encounter, Creature, WanderingTable, NPC
)
from app.domains.adventures.passes.base import BasePass

logger = logging.getLogger(__name__)


PASS3_ENCOUNTERS_PROMPT = """You are extracting encounters and threats from a tabletop RPG adventure module (B/X D&D or OSR).

## ADVENTURE CONTEXT
{context}

## YOUR TASK
Given the locations you now know about, extract ALL encounters and monsters:

### FIXED ENCOUNTERS
Monsters stationed in specific rooms. For each:
- location_key: Which room (must match a known location)
- name: Encounter name
- creatures: Full stat blocks for each creature type
- behavior: What are they doing when found?
- tactics: How do they fight?
- treasure: What they carry/guard
- trigger_condition: What starts combat?

### NPCs
Named characters that can be interacted with:
- name: NPC name
- title: Role/title
- locations_mentioned: Where are they mentioned/found?
- description, appearance, personality
- motivation: What drives them?
- stats: Full B/X stats if combatant
- disposition: Starting attitude toward party

## STAT BLOCK FORMAT (B/X)
```json
{{
  "name": "Goblin",
  "count": "1d6",
  "hd": "1-1",
  "hp": 4,
  "ac": 6,
  "thac0": 19,
  "attacks": ["1 weapon"],
  "damage": ["1d6"],
  "save": "NM",
  "morale": 7,
  "mv": "60' (20')",
  "alignment": "C",
  "special": ["infravision 60'"],
  "xp": 5
}}
```

## OUTPUT FORMAT
```json
{{
  "fixed_encounters": [
    {{
      "location_key": "33",
      "name": "Goblin Barracks",
      "creatures": [{{...full stats...}}],
      "behavior": "Sleeping unless alerted",
      "tactics": "Attack in groups, one flees if losing",
      "treasure": [{{"item": "10 gp", "location": "hidden under bedding"}}],
      "trigger_condition": "Entering room or making noise",
      "xp_value": 50
    }}
  ],
  "npcs": [
    {{
      "name": "Rogahn",
      "title": "Warrior Lord",
      "locations_mentioned": ["25", "26", "27"],
      "description": "A legendary warrior who built this stronghold...",
      "appearance": "Tall, broad-shouldered...",
      "personality": "Brave but reckless",
      "motivation": "Glory and wealth",
      "goals": ["Build an empire", "Find magical weapons"],
      "stats": {{...if applicable...}},
      "equipment": ["Sword +1", "Plate mail"],
      "disposition": "N/A - not present"
    }}
  ]
}}
```

## TEXT TO ANALYZE
{text}
"""


class InhabitantsPass(BasePass):
    """Pass 3: Extract encounters and NPCs."""

    name = "pass3_inhabitants"
    description = "Extract encounters and NPCs"

    async def execute(
        self,
        module: AdventureModule,
        full_text: str,
        preprocessed: Dict[str, Any],
        context: ExtractionContext,
    ) -> ExtractionContext:
        """Extract encounters and NPCs.

        Input: Overview + locations context
        Output: Encounters keyed by location, wandering tables, NPCs
        """
        self._log("Extracting inhabitants and threats...")
        updates = ExtractionContext()

        # First, save preprocessed wandering tables
        wandering_tables = preprocessed.get('wandering_tables', [])
        if wandering_tables:
            self._log(f"Saving {len(wandering_tables)} preprocessed wandering tables")
            await self._save_wandering_encounters(module, wandering_tables, updates)

        # Build context from previous passes
        context_prompt = context.to_context_prompt([
            'overview', 'locations_summary'
        ])

        # Call LLM for fixed encounters and NPCs
        prompt = PASS3_ENCOUNTERS_PROMPT.replace("{context}", context_prompt)
        result = await self._call_llm(prompt, full_text, stage_name="pass3_inhabitants")

        if not result:
            self._log("WARNING: No inhabitants extracted")
            return updates

        # Process fixed encounters
        fixed_encounters = result.get('fixed_encounters', [])
        self._log(f"Found {len(fixed_encounters)} fixed encounters")

        for enc_data in fixed_encounters:
            location_key = enc_data.get('location_key')
            if not location_key:
                continue

            # Create Encounter for context
            creatures = []
            for c in enc_data.get('creatures', []):
                creatures.append(Creature(
                    name=c.get('name', 'Unknown'),
                    count=str(c.get('count', '1')),
                    hd=c.get('hd'),
                    hp=str(c.get('hp', '')) if c.get('hp') else None,
                    ac=self._safe_int(c.get('ac')),
                    thac0=self._safe_int(c.get('thac0')),
                    attacks=c.get('attacks', []),
                    damage=c.get('damage', []),
                    save=c.get('save'),
                    morale=self._safe_int(c.get('morale')),
                    mv=c.get('mv'),
                    alignment=c.get('alignment'),
                    special=c.get('special', []),
                    xp=self._safe_int(c.get('xp')),
                ))

            encounter = Encounter(
                location_key=location_key,
                name=enc_data.get('name', 'Encounter'),
                description=enc_data.get('description'),
                creatures=creatures,
                behavior=enc_data.get('behavior'),
                tactics=enc_data.get('tactics'),
                treasure=enc_data.get('treasure', []),
                trigger_condition=enc_data.get('trigger_condition'),
                xp_value=self._safe_int(enc_data.get('xp_value')),
                encounter_type='fixed',
            )

            if location_key not in updates.encounters:
                updates.encounters[location_key] = []
            updates.encounters[location_key].append(encounter)

            # Create database record
            await self._create_encounter_record(module, enc_data, EncounterType.FIXED)

        # Process NPCs
        npcs_data = result.get('npcs', [])
        self._log(f"Found {len(npcs_data)} NPCs")

        for npc_data in npcs_data:
            npc = NPC(
                name=npc_data.get('name', 'Unknown'),
                title=npc_data.get('title'),
                description=npc_data.get('description'),
                appearance=npc_data.get('appearance'),
                personality=npc_data.get('personality'),
                motivation=npc_data.get('motivation'),
                goals=npc_data.get('goals', []),
                dialogue_hooks=npc_data.get('dialogue_hooks', []),
                stats=npc_data.get('stats', {}),
                equipment=npc_data.get('equipment', []),
                treasure=npc_data.get('treasure', []),
                spells=npc_data.get('spells', []),
                faction=npc_data.get('faction'),
                initial_disposition=(npc_data.get('disposition', 'neutral') or 'neutral')[:50],
                is_unique=npc_data.get('is_unique', True),
                locations_mentioned=npc_data.get('locations_mentioned', []),
            )
            updates.npcs.append(npc)

            # Create database record
            await self._create_npc_record(module, npc_data)

        await self.db.flush()

        self._log(f"Extracted {len(fixed_encounters)} fixed encounters")
        self._log(f"Extracted {len(updates.npcs)} NPCs")

        return updates

    async def _save_wandering_encounters(
        self,
        module: AdventureModule,
        wandering_tables: List[Dict[str, Any]],
        updates: ExtractionContext,
    ) -> None:
        """Save preprocessed wandering monster tables."""
        total_entries = 0

        for table in wandering_tables:
            table_name = table.get('table_name', 'Wandering Monsters')
            die_roll = table.get('die_roll', '1d6')
            check_freq = table.get('check_frequency')
            level = table.get('dungeon_level', 1)

            # Add to context
            wt = WanderingTable(
                table_name=table_name,
                die_roll=die_roll,
                check_frequency=check_freq,
                dungeon_level=level,
                entries=table.get('entries', []),
            )
            updates.wandering_tables.append(wt)

            # Create database records
            for entry in table.get('entries', []):
                creatures = entry.get('creatures', [])
                if not creatures and entry.get('name'):
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
        self._log(f"Saved {total_entries} wandering monster entries")

    async def _create_encounter_record(
        self,
        module: AdventureModule,
        enc_data: Dict[str, Any],
        enc_type: EncounterType,
    ) -> Optional[AdventureEncounter]:
        """Create AdventureEncounter database record."""
        location_key = enc_data.get('location_key')

        # Find location ID
        location_id = None
        if location_key:
            result = await self.db.execute(
                select(AdventureLocation)
                .where(AdventureLocation.module_id == module.id)
                .where(AdventureLocation.location_key == str(location_key))
            )
            location = result.scalar_one_or_none()
            if location:
                location_id = location.id

        encounter = AdventureEncounter(
            module_id=module.id,
            location_id=location_id,
            encounter_type=enc_type,
            name=enc_data.get('name') or 'Encounter',
            description=enc_data.get('description'),
            creatures=enc_data.get('creatures') or [],
            tactics=enc_data.get('tactics'),
            treasure=enc_data.get('treasure') or [],
            xp_value=self._safe_int(enc_data.get('xp_value')),
            trigger_condition=enc_data.get('trigger_condition'),
        )

        self.db.add(encounter)
        return encounter

    async def _create_npc_record(
        self,
        module: AdventureModule,
        npc_data: Dict[str, Any],
    ) -> Optional[AdventureNPC]:
        """Create AdventureNPC database record."""
        # Find location ID from first mentioned location
        location_id = None
        locations = npc_data.get('locations_mentioned', [])
        if locations:
            result = await self.db.execute(
                select(AdventureLocation)
                .where(AdventureLocation.module_id == module.id)
                .where(AdventureLocation.location_key == str(locations[0]))
            )
            location = result.scalar_one_or_none()
            if location:
                location_id = location.id

        npc = AdventureNPC(
            module_id=module.id,
            location_id=location_id,
            name=npc_data.get('name', 'Unknown'),
            title=npc_data.get('title'),
            description=npc_data.get('description'),
            appearance=npc_data.get('appearance'),
            personality=npc_data.get('personality'),
            motivation=npc_data.get('motivation'),
            goals=npc_data.get('goals', []),
            dialogue_hooks=npc_data.get('dialogue_hooks', []),
            stats=npc_data.get('stats', {}),
            equipment=npc_data.get('equipment', []),
            treasure=npc_data.get('treasure', []),
            spells=npc_data.get('spells', []),
            faction=npc_data.get('faction'),
            initial_disposition=(npc_data.get('disposition', 'neutral') or 'neutral')[:50],
            is_unique=npc_data.get('is_unique', True),
        )

        self.db.add(npc)
        return npc
